from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from insightclass.backends.factory import build_backend
from insightclass.evaluation.experiments import collect_experiment_records
from insightclass.schemas import InferenceConfig
from insightclass.utils.serialization import load_yaml, save_yaml
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


def _build_camera_list(include_credentials: bool = False) -> list[dict]:
    cameras = []
    for group, ips in DEFAULT_CAMERA_GROUPS.items():
        for ip in ips:
            cam = {
                "ip": ip,
                "group": group,
                "group_label": "前视角" if group == "front" else "后视角",
                "rtsp_url": _build_rtsp_url(ip, DEFAULT_RTSP_USERNAME, DEFAULT_RTSP_PASSWORD, DEFAULT_RTSP_PORT),
                "note": "",
                "custom": False,
            }
            if include_credentials:
                cam["username"] = DEFAULT_RTSP_USERNAME
                cam["password"] = DEFAULT_RTSP_PASSWORD
                cam["port"] = DEFAULT_RTSP_PORT
            cameras.append(cam)
    for cam in _load_custom_cameras():
        entry = {
            "ip": cam["ip"],
            "group": cam.get("group", "custom"),
            "group_label": cam.get("note", "自定义") or "自定义",
            "rtsp_url": _build_rtsp_url(cam["ip"], cam.get("username", DEFAULT_RTSP_USERNAME), cam.get("password", DEFAULT_RTSP_PASSWORD), cam.get("port", DEFAULT_RTSP_PORT)),
            "note": cam.get("note", ""),
            "custom": True,
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
    cameras = _load_custom_cameras()
    if any(c["ip"] == ip for c in cameras):
        return JSONResponse({"error": f"Camera {ip} already exists"}, status_code=409)
    cam = {
        "ip": ip,
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
    if idx is None:
        return JSONResponse({"error": "Camera not found"}, status_code=404)
    cameras[idx].update({
        "username": body.get("username", cameras[idx].get("username", DEFAULT_RTSP_USERNAME)),
        "password": body.get("password", cameras[idx].get("password", DEFAULT_RTSP_PASSWORD)),
        "port": body.get("port", cameras[idx].get("port", DEFAULT_RTSP_PORT)),
        "note": body.get("note", cameras[idx].get("note", "")),
    })
    _save_custom_cameras(cameras)
    return JSONResponse({"ok": True}, media_type="application/json; charset=utf-8")


@app.delete("/api/cameras/{ip}")
async def delete_camera(ip: str):
    cameras = _load_custom_cameras()
    cameras = [c for c in cameras if c["ip"] != ip]
    _save_custom_cameras(cameras)
    return JSONResponse({"ok": True}, media_type="application/json; charset=utf-8")


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

    latency = (time.time() - t0) * 1000
    return FrameDetectionResponse(
        detections=detections,
        latency_ms=round(latency, 1),
        frame_width=int(w),
        frame_height=int(h),
    )
