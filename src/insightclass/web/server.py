from __future__ import annotations

import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from insightclass.backends.factory import build_backend
from insightclass.evaluation.experiments import collect_experiment_records
from insightclass.schemas import InferenceConfig
from insightclass.utils.serialization import load_yaml
from insightclass.web.model_cache import clear_cache, get_model, preload_model
from insightclass.web.schemas import (
    DetectionOut,
    ExperimentSummary,
    FrameDetectionResponse,
    FrameOut,
    VideoDetectionResponse,
)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

EXPERIMENTS_ROOT = Path("experiments")
CLASS_CONFIG = Path("configs/classes.yaml")
DEFAULT_CONFIDENCE = 0.25
DEFAULT_IOU = 0.45


def _find_default_weights() -> str | None:
    """Return the best.pt path from the first experiment found, or None."""
    records = collect_experiment_records(str(EXPERIMENTS_ROOT))
    if not records:
        return None
    first = records[0]
    exp_dir = EXPERIMENTS_ROOT / first["experiment_id"] / "weights" / "best.pt"
    if exp_dir.exists():
        return str(exp_dir.resolve())
    return None


def _load_class_display_names() -> dict[str, str]:
    if not CLASS_CONFIG.exists():
        return {}
    data = load_yaml(str(CLASS_CONFIG))
    raw = data.get("display_names", {})
    return {str(k): str(v) for k, v in raw.items()}


def _get_experiments() -> list[dict]:
    records = collect_experiment_records(str(EXPERIMENTS_ROOT))
    FIXED_KEYS = {"experiment_id", "backend", "model_weights", "data_version", "class_names"}
    summaries: list[dict] = []
    for r in records:
        weights = EXPERIMENTS_ROOT / r["experiment_id"] / "weights" / "best.pt"
        # Separate metrics from fixed keys
        metrics = {k: v for k, v in r.items() if k not in FIXED_KEYS}
        class_names = r.get("class_names", "")
        if isinstance(class_names, str):
            class_names = [n for n in class_names.split(",") if n]
        summaries.append({
            "experiment_id": r["experiment_id"],
            "weights_path": str(weights.resolve()) if weights.exists() else "",
            "class_names": class_names,
            "metrics": metrics,
        })
    return summaries


def _extract_detections(result, display_names: dict[str, str]) -> list[DetectionOut]:
    detections: list[DetectionOut] = []
    if result.boxes is None:
        return detections
    boxes = result.boxes
    xyxy = boxes.xyxy.cpu().numpy()
    confs = boxes.conf.cpu().numpy()
    cls_ids = boxes.cls.cpu().numpy().astype(int)
    names = result.names if result.names else {}
    for i in range(len(xyxy)):
        class_id = int(cls_ids[i])
        class_name = str(names.get(class_id, str(class_id)))
        conf = float(confs[i])
        detections.append(DetectionOut(
            xyxy=xyxy[i].tolist(),
            confidence=round(conf, 4),
            class_id=class_id,
            class_name=class_name,
            display_name=display_names.get(class_name, class_name),
        ))
    return detections


@asynccontextmanager
async def lifespan(app: FastAPI):
    default_weights = _find_default_weights()
    if default_weights:
        preload_model(default_weights)
    yield
    clear_cache()


app = FastAPI(title="InsightClass Web", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    experiments = _get_experiments()
    display_names = _load_class_display_names()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "experiments": experiments,
            "display_names": display_names,
            "default_confidence": DEFAULT_CONFIDENCE,
            "default_iou": DEFAULT_IOU,
        },
    )


@app.get("/api/experiments")
async def list_experiments():
    experiments = _get_experiments()
    return [
        ExperimentSummary(
            experiment_id=r["experiment_id"],
            weights_path=r.get("weights_path", ""),
            class_names=r.get("class_names", []),
            metrics=r.get("metrics", {}),
        )
        for r in experiments
    ]


@app.post("/api/detect/frame")
async def detect_frame(
    image: UploadFile = File(...),
    model: str = Form(default=""),
    confidence: float = Form(default=DEFAULT_CONFIDENCE),
    iou: float = Form(default=DEFAULT_IOU),
):
    t0 = time.time()

    weights_path = model if model else (_find_default_weights() or "")
    yolo = get_model(weights_path)

    contents = await image.read()
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        results = yolo.predict(source=tmp_path, conf=confidence, iou=iou, verbose=False, stream=False, save=False)
        display_names = _load_class_display_names()

        if results and len(results) > 0:
            detections = _extract_detections(results[0], display_names)
            h, w = results[0].orig_shape
        else:
            detections = []
            h, w = 0, 0
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    latency = (time.time() - t0) * 1000
    return FrameDetectionResponse(
        detections=detections,
        latency_ms=round(latency, 1),
        frame_width=int(w),
        frame_height=int(h),
    )


@app.post("/api/detect/upload")
async def detect_upload(
    video: UploadFile = File(...),
    model: str = Form(default=""),
    confidence: float = Form(default=DEFAULT_CONFIDENCE),
    iou: float = Form(default=DEFAULT_IOU),
):
    t0 = time.time()

    weights_path = model if model else (_find_default_weights() or "")

    suffix = Path(video.filename).suffix if video.filename else ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        contents = await video.read()
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        cap = cv2.VideoCapture(tmp_path)
        video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        config = InferenceConfig(
            backend="ultralytics",
            weights_path=weights_path,
            source=tmp_path,
            output_dir=str(Path(tempfile.mkdtemp())),
            confidence=confidence,
            iou=iou,
            device="cpu",
            save_frames=False,
            save_video=False,
        )
        backend = build_backend("ultralytics")
        predictions = backend.load_predictions_as_sv_detections(config)

        display_names = _load_class_display_names()
        frames_out: list[FrameOut] = []
        for fp in predictions:
            dets = [
                DetectionOut(
                    xyxy=d.xyxy,
                    confidence=d.confidence,
                    class_id=d.class_id,
                    class_name=d.class_name,
                    display_name=display_names.get(d.class_name, d.class_name),
                )
                for d in fp.detections
            ]
            frames_out.append(FrameOut(frame_index=fp.frame_index, detections=dets))
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    total_latency = round(time.time() - t0, 2)
    return VideoDetectionResponse(
        frames=frames_out,
        frame_count=frame_count,
        fps=round(video_fps, 2),
        total_latency_sec=total_latency,
        video_width=video_width,
        video_height=video_height,
    )
