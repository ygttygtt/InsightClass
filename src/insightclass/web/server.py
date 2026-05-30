from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import random
import re
import tempfile
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from insightclass.backends.factory import build_backend
from insightclass.evaluation.experiments import collect_experiment_records
from insightclass.schemas import InferenceConfig
from insightclass.utils.serialization import load_yaml, save_yaml
from insightclass.web.model_cache import clear_cache, get_model, preload_model
from insightclass.web.schemas import (
    BatchDetectionResult,
    BatchJob,
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
CAMERAS_CONFIG = Path("configs/cameras.yaml")
APP_CONFIG = Path("configs/app.yaml")
DEFAULT_CONFIDENCE = 0.25
DEFAULT_IOU = 0.45

DEFAULT_CAMERA_GROUPS = {
    "front": [
        "10.8.14.36", "10.8.14.34", "10.8.14.30", "10.8.14.10",
        "10.8.14.18", "10.8.14.26", "10.8.14.28",
    ],
    "rear": [
        "10.8.14.5", "10.8.14.29", "10.8.14.21", "10.8.14.19",
        "10.8.14.17", "10.8.14.11", "10.8.14.22", "10.8.14.24", "10.8.14.32",
    ],
}
DEFAULT_RTSP_USERNAME = "admin"
DEFAULT_RTSP_PASSWORD = "1000phone"
DEFAULT_RTSP_PORT = 554

_rtsp_lock = threading.Lock()


class RtspStreamManager:
    """Manages a persistent RTSP connection and serves MJPEG frames."""

    def __init__(self):
        self._cap: cv2.VideoCapture | None = None
        self._url: str = ""
        self._frame: bytes | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._status: str = "idle"  # idle / connecting / streaming / error
        self._error: str = ""

    def start(self, rtsp_url: str) -> bool:
        if self._running and self._url == rtsp_url:
            return True
        self.stop()
        self._url = rtsp_url
        self._running = True
        self._status = "connecting"
        self._error = ""
        self._frame = None
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        if self._cap:
            self._cap.release()
            self._cap = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        self._status = "idle"
        self._error = ""
        with self._lock:
            self._frame = None

    def get_frame(self) -> bytes | None:
        with self._lock:
            return self._frame

    def get_status(self) -> dict:
        return {"status": self._status, "error": self._error}

    def _capture_loop(self):
        with _rtsp_lock:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
        try:
            self._cap = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)
            if not self._cap.isOpened():
                self._status = "error"
                self._error = "无法连接摄像头，请检查 IP 地址和网络"
                self._running = False
                return
            self._status = "streaming"
            while self._running:
                ret, frame = self._cap.read()
                if not ret or frame is None:
                    time.sleep(0.1)
                    continue
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                with self._lock:
                    self._frame = buf.tobytes()
        except Exception as e:
            self._status = "error"
            self._error = str(e)
        finally:
            if self._cap:
                self._cap.release()
                self._cap = None


_stream_manager = RtspStreamManager()

_batch_jobs: dict[str, dict] = {}


# ---- Dashboard Stats (in-memory) ----

class DashboardStats:
    """Tracks per-camera detection counts in memory."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cameras: dict[str, dict] = {}  # ip -> {stats, last_update}

    def record(self, ip: str, class_name: str):
        with self._lock:
            if ip not in self._cameras:
                self._cameras[ip] = {
                    "stats": {"phone_use": 0, "talking": 0, "sleeping": 0, "standing": 0},
                    "last_update": None,
                }
            cam = self._cameras[ip]
            if class_name in cam["stats"]:
                cam["stats"][class_name] += 1
            cam["last_update"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    def get_all(self) -> dict:
        with self._lock:
            cameras = []
            total = {"phone_use": 0, "talking": 0, "sleeping": 0, "standing": 0}
            for ip, data in self._cameras.items():
                cameras.append({
                    "ip": ip,
                    "stats": dict(data["stats"]),
                    "last_update": data["last_update"],
                })
                for k in total:
                    total[k] += data["stats"].get(k, 0)
            return {"cameras": cameras, "total": total}

    def reset(self):
        with self._lock:
            self._cameras.clear()


_dashboard_stats = DashboardStats()


def _validate_weights_path(path: str) -> str:
    """Restrict model paths to experiments directory."""
    p = Path(path).resolve()
    if not str(p).endswith(".pt"):
        raise ValueError("Only .pt weight files are allowed")
    if EXPERIMENTS_ROOT.resolve() not in p.parents and p.parent.resolve() != EXPERIMENTS_ROOT.resolve():
        raise ValueError(f"Model path must be under {EXPERIMENTS_ROOT}")
    return str(p)


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


_display_names_cache: dict[str, str] | None = None
_display_names_mtime: float = 0.0


def _load_class_display_names() -> dict[str, str]:
    global _display_names_cache, _display_names_mtime
    if not CLASS_CONFIG.exists():
        return {}
    mtime = CLASS_CONFIG.stat().st_mtime
    if _display_names_cache is not None and mtime == _display_names_mtime:
        return _display_names_cache
    data = load_yaml(str(CLASS_CONFIG))
    raw = data.get("display_names", {})
    _display_names_cache = {str(k): str(v) for k, v in raw.items()}
    _display_names_mtime = mtime
    return _display_names_cache


def _load_custom_cameras() -> list[dict]:
    if not CAMERAS_CONFIG.exists():
        return []
    data = load_yaml(str(CAMERAS_CONFIG))
    return data.get("cameras", [])


def _save_custom_cameras(cameras: list[dict]):
    CAMERAS_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    save_yaml(str(CAMERAS_CONFIG), {"cameras": cameras})


def _load_app_config() -> dict:
    if not APP_CONFIG.exists():
        return {}
    return load_yaml(str(APP_CONFIG))


def _save_app_config(cfg: dict):
    APP_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    save_yaml(str(APP_CONFIG), cfg)


def _get_default_model() -> str:
    cfg = _load_app_config()
    return cfg.get("default_model", "")


def _build_rtsp_url(ip: str, username: str, password: str, port: int) -> str:
    return f"rtsp://{username}:{password}@{ip}:{port}/Streaming/Channels/101"


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
    saved_model = _get_default_model()
    # Use saved model if valid, otherwise first experiment
    if not saved_model and experiments:
        saved_model = experiments[0].get("weights_path", "")
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "experiments": experiments,
            "display_names": display_names,
            "default_confidence": DEFAULT_CONFIDENCE,
            "default_iou": DEFAULT_IOU,
            "default_model": saved_model,
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


@app.get("/api/settings/default-model")
async def get_default_model():
    return JSONResponse({"model": _get_default_model()})


@app.post("/api/settings/default-model")
async def set_default_model(request: Request):
    body = await request.json()
    model = body.get("model", "")
    cfg = _load_app_config()
    cfg["default_model"] = model
    _save_app_config(cfg)
    return JSONResponse({"ok": True, "model": model})


@app.post("/api/detect/frame")
async def detect_frame(
    image: UploadFile = File(...),
    model: str = Form(default=""),
    confidence: float = Form(default=DEFAULT_CONFIDENCE),
    iou: float = Form(default=DEFAULT_IOU),
):
    t0 = time.time()

    contents = await image.read()
    detections = []
    h, w = 0, 0

    try:
        weights_path = model if model else (_find_default_weights() or "")
        if weights_path:
            weights_path = _validate_weights_path(weights_path)
        yolo = get_model(weights_path)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "frame.jpg"
            tmp_path.write_bytes(contents)
            results = yolo.predict(source=str(tmp_path), conf=confidence, iou=iou, verbose=False, stream=False, save=False)
            display_names = _load_class_display_names()

            if results and len(results) > 0:
                detections = _extract_detections(results[0], display_names)
                h, w = results[0].orig_shape
    except Exception:
        pass  # No model — return empty detections

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
    if weights_path:
        weights_path = _validate_weights_path(weights_path)

    suffix = Path(video.filename).suffix if video.filename else ".mp4"
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / f"video{suffix}"
        contents = await video.read()
        tmp_path.write_bytes(contents)

        cap = cv2.VideoCapture(str(tmp_path))
        video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        config = InferenceConfig(
            backend="ultralytics",
            weights_path=weights_path,
            source=str(tmp_path),
            output_dir=str(Path(tmp_dir) / "output"),
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

    total_latency = round(time.time() - t0, 2)
    return VideoDetectionResponse(
        frames=frames_out,
        frame_count=frame_count,
        fps=round(video_fps, 2),
        total_latency_sec=total_latency,
        video_width=video_width,
        video_height=video_height,
    )


# ---- Batch Video Detection ----

@app.post("/api/detect/batch-upload")
async def batch_upload(videos: list[UploadFile] = File(...)):
    batch_id = uuid.uuid4().hex[:12]
    tmp_dir = tempfile.mkdtemp(prefix="ic_batch_")
    items: list[dict] = []
    for idx, v in enumerate(videos):
        suffix = Path(v.filename).suffix if v.filename else ".mp4"
        display_name = Path(v.filename).name if v.filename else f"video{suffix}"
        tmp_path = Path(tmp_dir) / f"video_{idx}{suffix}"
        contents = await v.read()
        tmp_path.write_bytes(contents)
        items.append({
            "filename": display_name,
            "status": "pending",
            "frames": [],
            "frame_count": 0,
            "fps": 0,
            "video_width": 0,
            "video_height": 0,
            "latency_sec": 0,
            "error": "",
            "detection_summary": {},
            "_path": str(tmp_path),
        })
    _batch_jobs[batch_id] = {
        "batch_id": batch_id,
        "status": "pending",
        "items": items,
        "total_latency_sec": 0,
        "_dir": tmp_dir,
    }
    return JSONResponse({
        "batch_id": batch_id,
        "status": "pending",
        "item_count": len(items),
    })


@app.post("/api/detect/batch/{batch_id}")
async def batch_detect(
    batch_id: str,
    model: str = Form(default=""),
    confidence: float = Form(default=DEFAULT_CONFIDENCE),
    iou: float = Form(default=DEFAULT_IOU),
):
    job = _batch_jobs.get(batch_id)
    if not job:
        return JSONResponse({"error": "Batch not found"}, status_code=404)

    weights_path = model if model else (_find_default_weights() or "")
    if weights_path:
        weights_path = _validate_weights_path(weights_path)

    job["status"] = "processing"
    job["_weights_path"] = weights_path
    job["_confidence"] = confidence
    job["_iou"] = iou

    # Start background processing
    thread = threading.Thread(target=_batch_detect_worker, args=(job,), daemon=True)
    thread.start()

    return JSONResponse({"ok": True, "status": "processing"})


def _batch_detect_worker(job: dict):
    """Background worker for batch detection — runs sequentially, updates status per item."""
    weights_path = job["_weights_path"]
    confidence = job["_confidence"]
    iou = job["_iou"]

    t0 = time.time()
    display_names = _load_class_display_names()
    backend = build_backend("ultralytics")

    for i, item in enumerate(job["items"]):
        item["status"] = "processing"
        item["_index"] = i
        try:
            video_path = item["_path"]
            cap = cv2.VideoCapture(video_path)
            item["fps"] = round(cap.get(cv2.CAP_PROP_FPS) or 30.0, 2)
            item["video_width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            item["video_height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            item["frame_count"] = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()

            t1 = time.time()
            config = InferenceConfig(
                backend="ultralytics",
                weights_path=weights_path,
                source=video_path,
                output_dir=os.path.join(job["_dir"], "output"),
                confidence=confidence,
                iou=iou,
                device="cpu",
                save_frames=False,
                save_video=False,
            )
            predictions = backend.load_predictions_as_sv_detections(config)

            frames_out: list[dict] = []
            summary: dict[str, int] = {}
            for fp in predictions:
                dets = []
                for d in fp.detections:
                    dets.append(DetectionOut(
                        xyxy=d.xyxy,
                        confidence=d.confidence,
                        class_id=d.class_id,
                        class_name=d.class_name,
                        display_name=display_names.get(d.class_name, d.class_name),
                    ).model_dump())
                    summary[d.class_name] = summary.get(d.class_name, 0) + 1
                frames_out.append({"frame_index": fp.frame_index, "detections": dets})

            item["frames"] = frames_out
            item["detection_summary"] = summary
            item["latency_sec"] = round(time.time() - t1, 2)
            item["status"] = "done"
        except Exception as e:
            item["status"] = "error"
            item["error"] = str(e)

    job["status"] = "done"
    job["total_latency_sec"] = round(time.time() - t0, 2)


@app.get("/api/detect/batch/{batch_id}")
async def batch_status(batch_id: str):
    job = _batch_jobs.get(batch_id)
    if not job:
        return JSONResponse({"error": "Batch not found"}, status_code=404)
    return JSONResponse(_batch_response(job))


@app.get("/api/detect/batch/{batch_id}/item/{index}")
async def batch_item_detail(batch_id: str, index: int):
    job = _batch_jobs.get(batch_id)
    if not job:
        return JSONResponse({"error": "Batch not found"}, status_code=404)
    if index < 0 or index >= len(job["items"]):
        return JSONResponse({"error": "Item index out of range"}, status_code=400)
    item = job["items"][index]
    return JSONResponse({
        "filename": item["filename"],
        "status": item["status"],
        "frames": item["frames"],
        "frame_count": item["frame_count"],
        "fps": item["fps"],
        "video_width": item["video_width"],
        "video_height": item["video_height"],
        "latency_sec": item["latency_sec"],
        "error": item["error"],
        "detection_summary": item["detection_summary"],
    })


@app.get("/api/detect/batch/{batch_id}/export")
async def batch_export(batch_id: str, format: str = Query(default="json")):
    job = _batch_jobs.get(batch_id)
    if not job:
        return JSONResponse({"error": "Batch not found"}, status_code=404)

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["filename", "frame_index", "class_name", "display_name", "confidence", "x1", "y1", "x2", "y2"])
        for item in job["items"]:
            if item["status"] != "done":
                continue
            for frame in item["frames"]:
                for det in frame["detections"]:
                    writer.writerow([
                        item["filename"],
                        frame["frame_index"],
                        det["class_name"],
                        det.get("display_name", det["class_name"]),
                        det["confidence"],
                        det["xyxy"][0], det["xyxy"][1],
                        det["xyxy"][2], det["xyxy"][3],
                    ])
        content = output.getvalue()
        output.close()
        filename = f"batch_{batch_id}_detections.csv"
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # JSON format
    export_data = {
        "batch_id": batch_id,
        "total_latency_sec": job["total_latency_sec"],
        "items": [
            {
                "filename": item["filename"],
                "status": item["status"],
                "frame_count": item["frame_count"],
                "fps": item["fps"],
                "video_width": item["video_width"],
                "video_height": item["video_height"],
                "latency_sec": item["latency_sec"],
                "detection_summary": item["detection_summary"],
                "frames": item["frames"] if item["status"] == "done" else [],
            }
            for item in job["items"]
        ],
    }
    content = json.dumps(export_data, ensure_ascii=False, indent=2)
    filename = f"batch_{batch_id}_detections.json"
    return Response(
        content=content,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _batch_response(job: dict) -> dict:
    return {
        "batch_id": job["batch_id"],
        "status": job["status"],
        "total_latency_sec": job["total_latency_sec"],
        "items": [
            {
                "filename": item["filename"],
                "status": item["status"],
                "frame_count": item["frame_count"],
                "fps": item["fps"],
                "video_width": item["video_width"],
                "video_height": item["video_height"],
                "latency_sec": item["latency_sec"],
                "error": item.get("error", ""),
                "detection_summary": item.get("detection_summary", {}),
            }
            for item in job["items"]
        ],
    }


def _build_camera_list(include_credentials: bool = False) -> list[dict]:
    # Build a lookup of custom camera entries by IP for alias merging
    custom_cameras = _load_custom_cameras()
    custom_by_ip = {c["ip"]: c for c in custom_cameras}

    # Set of all default camera IPs for filtering
    default_ips = set()
    for ips in DEFAULT_CAMERA_GROUPS.values():
        default_ips.update(ips)

    # Determine which IP is currently streaming (if any)
    streaming_ip = None
    if _stream_manager._url and _stream_manager._status in ("connecting", "streaming"):
        # Extract IP from rtsp://user:pass@IP:port/...
        _m = re.search(r"@(\d+\.\d+\.\d+\.\d+)", _stream_manager._url)
        if _m:
            streaming_ip = _m.group(1)

    cameras = []
    for group, ips in DEFAULT_CAMERA_GROUPS.items():
        for ip in ips:
            custom = custom_by_ip.get(ip)
            cam = {
                "ip": ip,
                "name": custom.get("name", "") if custom else "",
                "group": group,
                "group_label": "前视角" if group == "front" else "后视角",
                "rtsp_url": _build_rtsp_url(ip, DEFAULT_RTSP_USERNAME, DEFAULT_RTSP_PASSWORD, DEFAULT_RTSP_PORT),
                "note": custom.get("note", "") if custom else "",
                "custom": False,
                "_status": "connected" if ip == streaming_ip else "disconnected",
            }
            if include_credentials:
                cam["username"] = DEFAULT_RTSP_USERNAME
                cam["password"] = DEFAULT_RTSP_PASSWORD
                cam["port"] = DEFAULT_RTSP_PORT
            cameras.append(cam)
    for cam in custom_cameras:
        # Skip custom entries that are just alias overrides for default cameras
        if cam["ip"] in default_ips:
            continue
        entry = {
            "ip": cam["ip"],
            "name": cam.get("name", ""),
            "group": cam.get("group", "custom"),
            "group_label": cam.get("note", "自定义") or "自定义",
            "rtsp_url": _build_rtsp_url(cam["ip"], cam.get("username", DEFAULT_RTSP_USERNAME), cam.get("password", DEFAULT_RTSP_PASSWORD), cam.get("port", DEFAULT_RTSP_PORT)),
            "note": cam.get("note", ""),
            "custom": True,
            "_status": "connected" if cam["ip"] == streaming_ip else "disconnected",
        }
        if include_credentials:
            entry["username"] = cam.get("username", DEFAULT_RTSP_USERNAME)
            entry["password"] = cam.get("password", DEFAULT_RTSP_PASSWORD)
            entry["port"] = cam.get("port", DEFAULT_RTSP_PORT)
        cameras.append(entry)
    return cameras


@app.get("/api/cameras")
async def list_cameras():
    return JSONResponse(content=_build_camera_list(), media_type="application/json; charset=utf-8")


@app.post("/api/cameras")
async def add_camera(request: Request):
    body = await request.json()
    ip = body.get("ip", "").strip()
    if not ip:
        return JSONResponse({"error": "IP is required"}, status_code=400)
    # Check if IP is a default camera
    default_ips = set()
    for ips in DEFAULT_CAMERA_GROUPS.values():
        default_ips.update(ips)
    if ip in default_ips:
        return JSONResponse({"error": f"Camera {ip} is a built-in camera, use edit to change its alias"}, status_code=409)
    cameras = _load_custom_cameras()
    if any(c["ip"] == ip for c in cameras):
        return JSONResponse({"error": f"Camera {ip} already exists"}, status_code=409)
    cam = {
        "ip": ip,
        "name": body.get("name", "").strip(),
        "username": body.get("username", DEFAULT_RTSP_USERNAME),
        "password": body.get("password", DEFAULT_RTSP_PASSWORD),
        "port": body.get("port", DEFAULT_RTSP_PORT),
        "note": body.get("note", ""),
    }
    cameras.append(cam)
    _save_custom_cameras(cameras)
    return JSONResponse({"ok": True, "camera": cam}, media_type="application/json; charset=utf-8")


@app.put("/api/cameras/{ip}")
async def update_camera(ip: str, request: Request):
    body = await request.json()
    cameras = _load_custom_cameras()
    idx = next((i for i, c in enumerate(cameras) if c["ip"] == ip), None)

    # Check if this is a default camera (not yet in custom list)
    default_ips = set()
    for ips in DEFAULT_CAMERA_GROUPS.values():
        default_ips.update(ips)
    is_default = ip in default_ips

    if idx is not None:
        # Update existing custom entry
        cameras[idx].update({
            "name": body.get("name", cameras[idx].get("name", "")),
            "username": body.get("username", cameras[idx].get("username", DEFAULT_RTSP_USERNAME)),
            "password": body.get("password", cameras[idx].get("password", DEFAULT_RTSP_PASSWORD)),
            "port": body.get("port", cameras[idx].get("port", DEFAULT_RTSP_PORT)),
            "note": body.get("note", cameras[idx].get("note", "")),
        })
    elif is_default:
        # Create a custom entry to store alias/overrides for a default camera
        cameras.append({
            "ip": ip,
            "name": body.get("name", ""),
            "username": body.get("username", DEFAULT_RTSP_USERNAME),
            "password": body.get("password", DEFAULT_RTSP_PASSWORD),
            "port": body.get("port", DEFAULT_RTSP_PORT),
            "note": body.get("note", ""),
        })
    else:
        return JSONResponse({"error": "Camera not found"}, status_code=404)

    _save_custom_cameras(cameras)
    return JSONResponse({"ok": True}, media_type="application/json; charset=utf-8")


@app.delete("/api/cameras/{ip}")
async def delete_camera(ip: str):
    cameras = _load_custom_cameras()
    cameras = [c for c in cameras if c["ip"] != ip]
    _save_custom_cameras(cameras)
    return JSONResponse({"ok": True}, media_type="application/json; charset=utf-8")


@app.get("/api/cameras/{ip}/test")
async def test_single_camera(ip: str):
    """Test connectivity for a single camera, return result immediately."""
    cameras = _build_camera_list(include_credentials=True)
    cam = next((c for c in cameras if c["ip"] == ip), None)
    if not cam:
        return JSONResponse({"error": "Camera not found"}, status_code=404)
    rtsp_url = cam.get("rtsp_url", "")
    ok = await asyncio.to_thread(_test_camera_connection, rtsp_url)
    return JSONResponse({"ip": ip, "status": "connected" if ok else "disconnected"})


@app.post("/api/cameras/test")
async def test_cameras(request: Request):
    body = await request.json()
    camera_list = body.get("cameras", [])
    if not camera_list:
        camera_list = _build_camera_list(include_credentials=True)

    async def _test_one(cam):
        if isinstance(cam, dict):
            ip = cam["ip"]
            rtsp_url = cam.get("rtsp_url", _build_rtsp_url(ip, DEFAULT_RTSP_USERNAME, DEFAULT_RTSP_PASSWORD, DEFAULT_RTSP_PORT))
        else:
            ip = str(cam)
            rtsp_url = _build_rtsp_url(ip, DEFAULT_RTSP_USERNAME, DEFAULT_RTSP_PASSWORD, DEFAULT_RTSP_PORT)
        ok = await asyncio.to_thread(_test_camera_connection, rtsp_url)
        return ip, "connected" if ok else "disconnected"

    results_list = await asyncio.gather(*[_test_one(cam) for cam in camera_list])
    return JSONResponse(dict(results_list), media_type="application/json; charset=utf-8")


def _test_camera_connection(rtsp_url: str) -> bool:
    try:
        with _rtsp_lock:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            return False
        ret, frame = cap.read()
        cap.release()
        return ret and frame is not None
    except Exception:
        return False


@app.get("/api/stream/rtsp")
async def stream_rtsp(rtsp_url: str):
    """MJPEG stream — one persistent connection, no base64 overhead."""

    def generate():
        _stream_manager.start(rtsp_url)
        while True:
            frame = _stream_manager.get_frame()
            if frame:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )
            else:
                time.sleep(0.05)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.post("/api/stream/stop")
async def stream_stop():
    _stream_manager.stop()
    return JSONResponse({"ok": True})


@app.get("/api/stream/status")
async def stream_status():
    return JSONResponse(_stream_manager.get_status())


@app.post("/api/detect/rtsp")
async def detect_rtsp(
    rtsp_url: str = Form(...),
    model: str = Form(default=""),
    confidence: float = Form(default=DEFAULT_CONFIDENCE),
    iou: float = Form(default=DEFAULT_IOU),
):
    t0 = time.time()

    # Ensure stream is running for this URL
    _stream_manager.start(rtsp_url)

    # Grab the latest frame from the persistent stream
    frame_bytes = _stream_manager.get_frame()
    if not frame_bytes:
        return FrameDetectionResponse(detections=[], latency_ms=0, frame_width=0, frame_height=0)

    # Decode frame for YOLO inference
    arr = np.frombuffer(frame_bytes, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        return FrameDetectionResponse(detections=[], latency_ms=0, frame_width=0, frame_height=0)

    h, w = frame.shape[:2]
    detections = []
    try:
        weights_path = model if model else (_find_default_weights() or "")
        if weights_path:
            weights_path = _validate_weights_path(weights_path)
        yolo = get_model(weights_path)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "frame.jpg"
            cv2.imwrite(str(tmp_path), frame)
            results = yolo.predict(source=str(tmp_path), conf=confidence, iou=iou, verbose=False, stream=False, save=False)
            display_names = _load_class_display_names()

            if results and len(results) > 0:
                detections = _extract_detections(results[0], display_names)
                h, w = results[0].orig_shape
    except Exception:
        pass

    # Record dashboard stats
    cam_ip = _extract_ip_from_rtsp(rtsp_url)
    for det in detections:
        _dashboard_stats.record(cam_ip, det.class_name)

    latency = (time.time() - t0) * 1000
    return FrameDetectionResponse(
        detections=detections,
        latency_ms=round(latency, 1),
        frame_width=int(w),
        frame_height=int(h),
    )


def _extract_ip_from_rtsp(url: str) -> str:
    """Extract IP address from rtsp://user:pass@IP:port/... URL."""
    try:
        after_at = url.split("@", 1)[1] if "@" in url else url.split("//", 1)[1]
        return after_at.split(":")[0].split("/")[0]
    except Exception:
        return "unknown"


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html")


@app.get("/api/dashboard/stats")
async def dashboard_stats():
    raw = _dashboard_stats.get_all()
    cameras = _build_camera_list()
    # Build a lookup from raw stats by IP
    stats_by_ip = {c["ip"]: c for c in raw["cameras"]}
    result_cameras = []
    for cam in cameras:
        ip = cam["ip"]
        data = stats_by_ip.get(ip, {"stats": {"phone_use": 0, "talking": 0, "sleeping": 0, "standing": 0}, "last_update": None})
        result_cameras.append({
            "ip": ip,
            "name": cam.get("name") or cam.get("group_label", ""),
            "group": cam.get("group", "custom"),
            "group_label": cam.get("group_label", "自定义"),
            "online": cam.get("_status", "unknown") == "connected",
            "stats": data["stats"],
            "last_update": data["last_update"],
        })
    return JSONResponse({
        "cameras": result_cameras,
        "total": raw["total"],
        "online_count": sum(1 for c in result_cameras if c["online"]),
        "total_cameras": len(result_cameras),
    })


@app.get("/api/dashboard/report")
async def dashboard_report_get():
    return await _generate_report()


@app.post("/api/dashboard/report")
async def dashboard_report_post():
    return await _generate_report()


async def _generate_report():
    raw = _dashboard_stats.get_all()
    cameras = _build_camera_list()
    stats_by_ip = {c["ip"]: c for c in raw["cameras"]}
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["camera_ip", "camera_name", "phone_use", "talking", "sleeping", "standing", "total", "timestamp"])
    for cam in cameras:
        ip = cam["ip"]
        data = stats_by_ip.get(ip, {"stats": {"phone_use": 0, "talking": 0, "sleeping": 0, "standing": 0}, "last_update": ""})
        s = data["stats"]
        total = sum(s.values())
        writer.writerow([ip, cam.get("name", ""), s["phone_use"], s["talking"], s["sleeping"], s["standing"], total, data["last_update"] or ""])
    content = output.getvalue()
    output.close()
    filename = f"dashboard_report_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/dashboard/history")
async def dashboard_history():
    """Return 24h simulated historical data per camera for chart display."""
    cameras = _build_camera_list()
    now = time.time()
    history: dict[str, list] = {}
    for cam in cameras:
        ip = cam["ip"]
        points = []
        for h in range(24):
            t = now - (23 - h) * 3600
            hour = time.localtime(t).tm_hour
            # More activity during class hours (8-18)
            base = random.randint(2, 15) if 8 <= hour <= 18 else random.randint(0, 3)
            points.append({
                "time": time.strftime("%Y-%m-%dT%H:00:00", time.localtime(t)),
                "phone_use": random.randint(0, base),
                "talking": random.randint(0, base),
                "sleeping": random.randint(0, max(1, base // 2)),
                "standing": random.randint(0, max(1, base // 3)),
            })
        history[ip] = points
    return JSONResponse({"history": history})
