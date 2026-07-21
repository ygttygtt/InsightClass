from __future__ import annotations

import asyncio
import base64
import csv
import ipaddress
import io
import json
import logging
import os
import re
import shutil
import socket
from datetime import datetime
import sys
import tempfile
import threading
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw, ImageFont

from insightclass.backends.factory import build_backend
from insightclass.backends.onnx_backend import OnnxBackend
from insightclass.utils.experiments import collect_experiment_records
from insightclass.schemas import InferenceConfig
from insightclass.utils.serialization import load_json, load_yaml, save_yaml
from insightclass.web.llm import (
    LlmClientError,
    OpenAICompatibleClient,
    OpenAICompatibleConfig,
)
from insightclass.web.model_cache import clear_cache, get_model, preload_model
from insightclass.web.schemas import (
    DetectionOut,
    FrameDetectionResponse,
    FrameOut,
    VideoDetectionResponse,
)

logger = logging.getLogger(__name__)

def _get_base_dir() -> Path:
    """打包后返回 exe 所在目录，开发模式返回 cwd。"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path.cwd()


def _get_resource_dir() -> Path:
    """打包后返回内部资源目录（_MEIPASS），开发模式返回项目根目录。"""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    # 开发模式：从 src/insightclass/web/server.py 向上 4 级到项目根
    return Path(__file__).parent.parent.parent.parent


_BASE_DIR = _get_base_dir()
_RESOURCE_DIR = _get_resource_dir()
_FRONTEND_DIST = _RESOURCE_DIR / "frontend" / "dist"
EXPERIMENTS_ROOT = _BASE_DIR / "experiments"
CLASS_CONFIG = _BASE_DIR / "configs" / "classes.yaml"
CAMERAS_CONFIG = _BASE_DIR / "configs" / "cameras.yaml"
APP_CONFIG = _BASE_DIR / "configs" / "app.yaml"
DEFAULT_CONFIDENCE = 0.5
DEFAULT_IOU = 0.45
DEFAULT_LLM_BASE_URL = "https://api.openai.com/v1"
UPLOAD_CHUNK_SIZE = 1024 * 1024
MAX_IMAGE_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_IMAGE_PIXELS = 50_000_000
MAX_VIDEO_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
MAX_BATCH_FILES = 20
MAX_BATCH_UPLOAD_BYTES = 8 * 1024 * 1024 * 1024
MAX_CSV_UPLOAD_BYTES = 5 * 1024 * 1024
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".webp"})
VIDEO_SUFFIXES = frozenset({".mp4", ".avi", ".mov", ".mkv", ".m4v", ".webm"})

# RTSP 默认凭据（可通过 Web 界面全局设置）
DEFAULT_RTSP_USERNAME = "admin"
DEFAULT_RTSP_PASSWORD = ""
DEFAULT_RTSP_PORT = 554

_rtsp_lock = threading.Lock()
_app_config_lock = threading.RLock()
_camera_config_lock = threading.RLock()
_FFMPEG_OPTIONS = "rtsp_transport;tcp|stimeout;5000000|rw_timeout;5000000"


class RtspStreamManager:
    """Manages a persistent RTSP connection and serves MJPEG frames."""

    def __init__(self):
        self._cap: cv2.VideoCapture | None = None
        self._url: str = ""
        self._frame: bytes | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._lifecycle_lock = threading.RLock()
        self._status: str = "idle"  # idle / connecting / streaming / error
        self._error: str = ""

    def start(self, rtsp_url: str) -> bool:
        with self._lifecycle_lock:
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
        with self._lifecycle_lock:
            self._running = False
            if self._cap:
                self._cap.release()
                self._cap = None
            if self._thread and self._thread is not threading.current_thread():
                self._thread.join(timeout=6)
            self._thread = None
            self._status = "idle"
            self._error = ""
            with self._lock:
                self._frame = None

    def get_frame(self) -> bytes | None:
        with self._lock:
            return self._frame

    def get_status(self) -> dict:
        return {
            "active": self._running and self._status == "streaming",
            "status": self._status,
            "error": self._error,
        }

    def _open_capture(self, rtsp_url: str | None = None):
        """Create a VideoCapture with short timeout."""
        with _rtsp_lock:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = _FFMPEG_OPTIONS
        timeout_params = [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
            5000,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC,
            5000,
        ]
        try:
            self._cap = cv2.VideoCapture(
                rtsp_url or self._url, cv2.CAP_FFMPEG, timeout_params
            )
        except (TypeError, cv2.error):
            self._cap = cv2.VideoCapture(rtsp_url or self._url, cv2.CAP_FFMPEG)

    def _capture_loop(self):
        try:
            self._open_capture()
            if not self._cap or not self._cap.isOpened():
                self._status = "error"
                self._error = "无法连接摄像头，请检查 IP 地址和网络"
                self._running = False
                return

            # Check for black frames and fallback to sub-stream (102)
            black_frame_count = 0
            for _ in range(10):  # Check first 10 frames
                ret, frame = self._cap.read()
                if ret and frame is not None:
                    mean_val = frame.mean()
                    if mean_val > 5:  # Not a black frame
                        break
                    black_frame_count += 1
                time.sleep(0.1)

            if black_frame_count >= 5:  # Most frames are black
                # Try sub-stream (102)
                sub_url = self._url.replace("/Channels/101", "/Channels/102")
                logger.info(f"主码流黑屏，尝试子码流: {sub_url}")
                if self._cap:
                    self._cap.release()
                    self._cap = None
                self._open_capture(sub_url)
                if not self._cap or not self._cap.isOpened():
                    self._status = "error"
                    self._error = "主码流黑屏，子码流连接失败"
                    self._running = False
                    return

            self._status = "streaming"
            fail_count = 0
            while self._running:
                ret, frame = self._cap.read()
                if not ret or frame is None:
                    fail_count += 1
                    if fail_count > 50:  # ~5 seconds of failures
                        # Attempt reconnect with retries
                        reconnected = False
                        for _ in range(3):
                            if not self._running:
                                return
                            if self._cap:
                                self._cap.release()
                                self._cap = None
                            time.sleep(2)
                            self._open_capture()
                            if self._cap and self._cap.isOpened():
                                reconnected = True
                                break
                        if not reconnected:
                            self._status = "error"
                            self._error = "摄像头连接中断，重连失败"
                            self._running = False
                            return
                        fail_count = 0
                    else:
                        time.sleep(0.1)
                    continue
                fail_count = 0
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                with self._lock:
                    self._frame = buf.tobytes()
        except Exception as e:
            self._status = "error"
            self._error = str(e)
        finally:
            self._running = False
            if self._cap:
                self._cap.release()
                self._cap = None


class RtspStreamRegistry:
    """Own one persistent capture per camera instead of one global stream."""

    def __init__(self, manager_factory=RtspStreamManager):
        self._manager_factory = manager_factory
        self._managers: dict[str, RtspStreamManager] = {}
        self._lock = threading.Lock()

    def start(self, camera_ip: str, rtsp_url: str) -> RtspStreamManager:
        with self._lock:
            manager = self._managers.get(camera_ip)
            if manager is None:
                manager = self._manager_factory()
                self._managers[camera_ip] = manager
        manager.start(rtsp_url)
        return manager

    def get(self, camera_ip: str) -> RtspStreamManager | None:
        with self._lock:
            return self._managers.get(camera_ip)

    def get_status(self, camera_ip: str) -> dict:
        manager = self.get(camera_ip)
        status = manager.get_status() if manager else {
            "active": False,
            "status": "idle",
            "error": "",
        }
        return {**status, "camera_ip": camera_ip}

    def is_active(self, camera_ip: str) -> bool:
        manager = self.get(camera_ip)
        if manager is None:
            return False
        return manager.get_status()["status"] in ("connecting", "streaming")

    def stop(self, camera_ip: str) -> None:
        with self._lock:
            manager = self._managers.pop(camera_ip, None)
        if manager:
            manager.stop()

    def stop_all(self) -> None:
        with self._lock:
            managers = list(self._managers.values())
            self._managers.clear()
        for manager in managers:
            manager.stop()


_stream_registry = RtspStreamRegistry()

_batch_jobs: dict[str, dict] = {}
_batch_jobs_lock = threading.RLock()


def _validate_upload_suffix(upload: UploadFile, allowed: frozenset[str], label: str) -> str:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in allowed:
        extensions = ", ".join(sorted(allowed))
        raise HTTPException(415, f"Unsupported {label} file type; allowed: {extensions}")
    return suffix


async def _read_upload_limited(upload: UploadFile, max_bytes: int, label: str) -> bytes:
    if upload.size is not None and upload.size > max_bytes:
        raise HTTPException(413, f"{label} exceeds the {max_bytes // (1024 * 1024)} MiB limit")
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(UPLOAD_CHUNK_SIZE):
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(413, f"{label} exceeds the {max_bytes // (1024 * 1024)} MiB limit")
        chunks.append(chunk)
    if total == 0:
        raise HTTPException(400, f"{label} is empty")
    return b"".join(chunks)


async def _write_upload_limited(
    upload: UploadFile, destination: Path, max_bytes: int, label: str
) -> int:
    if upload.size is not None and upload.size > max_bytes:
        raise HTTPException(413, f"{label} exceeds the {max_bytes // (1024 * 1024)} MiB limit")
    total = 0
    try:
        with destination.open("wb") as handle:
            while chunk := await upload.read(UPLOAD_CHUNK_SIZE):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        413, f"{label} exceeds the {max_bytes // (1024 * 1024)} MiB limit"
                    )
                handle.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    if total == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(400, f"{label} is empty")
    return total


def _clear_batch_jobs() -> None:
    with _batch_jobs_lock:
        jobs = list(_batch_jobs.values())
        _batch_jobs.clear()
    for job in jobs:
        tmp_dir = job.get("_dir")
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---- Dashboard Stats (in-memory) ----

class DashboardStats:
    """Tracks per-camera detection counts in memory."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cameras: dict[str, dict] = {}  # ip -> {stats, last_update}
        self._history: dict[str, dict[int, dict[str, int]]] = defaultdict(dict)

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
            bucket = int(time.time() // 3600 * 3600)
            hourly = self._history[ip].setdefault(bucket, {
                "phone_use": 0,
                "talking": 0,
                "sleeping": 0,
                "standing": 0,
            })
            if class_name in hourly:
                hourly[class_name] += 1
            cutoff = bucket - 23 * 3600
            self._history[ip] = {
                key: value
                for key, value in self._history[ip].items()
                if key >= cutoff
            }

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
            self._history.clear()

    def remove(self, ip: str) -> None:
        with self._lock:
            self._cameras.pop(ip, None)
            self._history.pop(ip, None)

    def get_history(self, ips: list[str]) -> dict[str, list[dict]]:
        with self._lock:
            now_bucket = int(time.time() // 3600 * 3600)
            buckets = [now_bucket - index * 3600 for index in range(23, -1, -1)]
            result: dict[str, list[dict]] = {}
            for ip in ips:
                by_hour = self._history.get(ip, {})
                result[ip] = []
                for bucket in buckets:
                    values = by_hour.get(bucket, {})
                    result[ip].append({
                        "time": time.strftime("%Y-%m-%dT%H:00:00", time.localtime(bucket)),
                        "phone_use": values.get("phone_use", 0),
                        "talking": values.get("talking", 0),
                        "sleeping": values.get("sleeping", 0),
                        "standing": values.get("standing", 0),
                    })
            return result


_dashboard_stats = DashboardStats()


def _is_onnx_model(path: str) -> bool:
    """Check if a model path points to an ONNX model."""
    return path.lower().endswith(".onnx")


def _validate_weights_path(path: str) -> str:
    """Restrict model paths to experiments or models directory."""
    p = Path(path).resolve()
    if not (str(p).endswith(".pt") or str(p).endswith(".onnx")):
        raise ValueError("Only .pt or .onnx weight files are allowed")
    if not p.is_file():
        raise FileNotFoundError(f"Model file not found: {p.name}")
    # 允许 experiments/ 目录
    if EXPERIMENTS_ROOT.resolve() in p.parents or p.parent.resolve() == EXPERIMENTS_ROOT.resolve():
        return str(p)
    # 允许内置 models/ 目录
    bundled_models = (_RESOURCE_DIR / "models").resolve()
    if bundled_models in p.parents or p.parent.resolve() == bundled_models:
        return str(p)
    # 允许用户目录下的 models/
    user_models = (_BASE_DIR / "models").resolve()
    if user_models in p.parents or p.parent.resolve() == user_models:
        return str(p)
    raise ValueError(f"Model path must be under {EXPERIMENTS_ROOT} or models/")


def _find_default_weights() -> str | None:
    """Return best weights path: prefer ONNX models, then .pt."""
    # 优先使用 ONNX 模型（打包时打入的，启动更快）
    bundled_onnx = _RESOURCE_DIR / "models" / "onnx"
    for onnx_file in bundled_onnx.glob("*.onnx"):
        return str(onnx_file.resolve())
    user_onnx = _BASE_DIR / "models" / "onnx"
    for onnx_file in user_onnx.glob("*.onnx"):
        return str(onnx_file.resolve())
    # 回退：内置 .pt 模型
    bundled = _RESOURCE_DIR / "models" / "best.pt"
    if bundled.exists():
        return str(bundled.resolve())
    # 回退：用户目录下的 models/
    user_models = _BASE_DIR / "models" / "best.pt"
    if user_models.exists():
        return str(user_models.resolve())
    # 回退：从 experiments 目录查找
    if not EXPERIMENTS_ROOT.exists():
        return None
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
    with _camera_config_lock:
        if not CAMERAS_CONFIG.exists():
            return []
        data = load_yaml(str(CAMERAS_CONFIG))
        cameras = data.get("cameras", [])
        return cameras if isinstance(cameras, list) else []


def _save_custom_cameras(cameras: list[dict]):
    with _camera_config_lock:
        CAMERAS_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        save_yaml(str(CAMERAS_CONFIG), {"cameras": cameras})


_camera_ping_results: dict[str, dict] = {}
_camera_ping_lock = threading.Lock()


def _probe_camera_port(ip: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            return sock.connect_ex((ip, port)) == 0
    except OSError:
        return False


async def _ping_cameras_once() -> None:
    cameras = _load_custom_cameras()
    port = int(_get_rtsp_credentials().get("port", DEFAULT_RTSP_PORT))
    probes = []
    for cam in cameras:
        try:
            ip = _validate_camera_ip(str(cam.get("ip", "")))
        except ValueError:
            continue
        probes.append((ip, asyncio.to_thread(_probe_camera_port, ip, port)))
    if not probes:
        return
    results = await asyncio.gather(*(probe for _, probe in probes))
    checked_at = datetime.now().isoformat()
    with _camera_ping_lock:
        for (ip, _), reachable in zip(probes, results, strict=False):
            _camera_ping_results[ip] = {
                "reachable": reachable,
                "last_check": checked_at,
            }


async def _ping_cameras_periodically():
    """Background task to check camera reachability every 30 seconds."""
    while True:
        await _ping_cameras_once()
        await asyncio.sleep(30)


def _load_app_config() -> dict:
    with _app_config_lock:
        if not APP_CONFIG.exists():
            return {}
        return load_yaml(str(APP_CONFIG))


def _save_app_config(cfg: dict):
    with _app_config_lock:
        APP_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        save_yaml(str(APP_CONFIG), cfg)


def _update_app_config(values: dict) -> dict:
    with _app_config_lock:
        cfg = _load_app_config()
        cfg.update(values)
        _save_app_config(cfg)
        return cfg


def _get_default_model() -> str:
    cfg = _load_app_config()
    return cfg.get("default_model", "")


def _find_startup_weights() -> str | None:
    """Prefer a valid saved model, then fall back to model discovery."""
    saved_model = _get_default_model()
    if saved_model:
        try:
            return _validate_weights_path(saved_model)
        except (FileNotFoundError, ValueError) as exc:
            logger.warning("Ignoring invalid saved default model: %s", exc)
    return _find_default_weights()


def _get_rtsp_credentials() -> dict:
    """获取全局 RTSP 凭据（从 app.yaml 读取，支持 Web 界面设置）。"""
    cfg = _load_app_config()
    creds = cfg.get("rtsp_credentials", {})
    return {
        "username": creds.get("username", DEFAULT_RTSP_USERNAME),
        "password": creds.get("password", DEFAULT_RTSP_PASSWORD),
        "port": creds.get("port", DEFAULT_RTSP_PORT),
    }


def _build_rtsp_url(ip: str, username: str = "", password: str = "", port: int = 0) -> str:
    """构建 RTSP URL。如果不传凭据，使用全局凭据。"""
    if not username:
        creds = _get_rtsp_credentials()
        username = creds["username"]
        password = creds["password"]
        port = port or creds["port"]
    _validate_camera_ip(ip)
    if not 1 <= int(port) <= 65535:
        raise ValueError("RTSP port must be between 1 and 65535")
    encoded_username = quote(str(username), safe="")
    encoded_password = quote(str(password), safe="")
    return (
        f"rtsp://{encoded_username}:{encoded_password}@{ip}:{int(port)}"
        "/Streaming/Channels/101"
    )


def _validate_camera_ip(ip: str) -> str:
    """Validate and normalize the IPv4 address used by camera endpoints."""
    try:
        parsed = ipaddress.ip_address(ip.strip())
    except ValueError as exc:
        raise ValueError("Invalid camera IP address") from exc
    if parsed.version != 4:
        raise ValueError("Only IPv4 camera addresses are supported")
    return str(parsed)


def _require_camera_ip(ip: str) -> str:
    try:
        return _validate_camera_ip(ip)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _resolve_camera_rtsp_url(camera_ip: str) -> str:
    normalized_ip = _validate_camera_ip(camera_ip)
    if not any(cam.get("ip") == normalized_ip for cam in _load_custom_cameras()):
        raise HTTPException(404, "Camera not found")
    return _build_rtsp_url(normalized_ip)


def _get_experiments() -> list[dict]:
    records = collect_experiment_records(str(EXPERIMENTS_ROOT))
    FIXED_KEYS = {"experiment_id", "backend", "model_weights", "data_version", "class_names"}
    summaries: list[dict] = []
    for r in records:
        exp_id = r["experiment_id"]
        exp_dir = EXPERIMENTS_ROOT / exp_id
        weights = exp_dir / "weights" / "best.pt"
        record_path = exp_dir / "experiment_record.json"
        full_record = load_json(record_path) if record_path.exists() else {}
        # Separate metrics from fixed keys
        metrics = {k: v for k, v in r.items() if k not in FIXED_KEYS}
        class_names = r.get("class_names", "")
        if isinstance(class_names, str):
            class_names = [n for n in class_names.split(",") if n]
        summaries.append({
            "experiment_id": exp_id,
            "weights_path": str(weights.resolve()) if weights.exists() else "",
            "class_names": class_names,
            "hyperparameters": full_record.get("hyperparameters", {}),
            "metrics": metrics,
            "has_results_csv": (exp_dir / "results.csv").exists(),
            "has_confusion_matrix": (exp_dir / "confusion_matrix.png").exists(),
            "has_results_png": (exp_dir / "results.png").exists(),
        })

    # If no experiments found, discover models from models/ directory
    if not summaries:
        models_dir = _RESOURCE_DIR / "models"
        user_models_dir = _BASE_DIR / "models"
        for search_dir in [models_dir, user_models_dir]:
            if not search_dir.exists():
                continue
            # Find ONNX models
            for onnx_file in sorted(search_dir.glob("*.onnx")):
                summaries.append({
                    "experiment_id": onnx_file.stem,
                    "weights_path": str(onnx_file.resolve()),
                    "class_names": ["phone_use", "talking", "sleeping", "standing"],
                    "hyperparameters": {},
                    "metrics": {},
                    "has_results_csv": False,
                    "has_confusion_matrix": False,
                    "has_results_png": False,
                })
            # Find .pt models
            for pt_file in sorted(search_dir.glob("*.pt")):
                summaries.append({
                    "experiment_id": pt_file.stem,
                    "weights_path": str(pt_file.resolve()),
                    "class_names": ["phone_use", "talking", "sleeping", "standing"],
                    "hyperparameters": {},
                    "metrics": {},
                    "has_results_csv": False,
                    "has_confusion_matrix": False,
                    "has_results_png": False,
                })
            # Also check subdirectories (e.g., onnx/)
            for subdir in search_dir.iterdir():
                if subdir.is_dir():
                    for model_file in sorted(subdir.glob("*.onnx")) + sorted(subdir.glob("*.pt")):
                        summaries.append({
                            "experiment_id": f"{subdir.name}/{model_file.stem}",
                            "weights_path": str(model_file.resolve()),
                            "class_names": ["phone_use", "talking", "sleeping", "standing"],
                            "hyperparameters": {},
                            "metrics": {},
                            "has_results_csv": False,
                            "has_confusion_matrix": False,
                            "has_results_png": False,
                        })
    return summaries


def _get_font(size: int = 18) -> ImageFont.FreeTypeFont:
    """Get a font that supports Chinese characters."""
    font_paths = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    for p in font_paths:
        try:
            return ImageFont.truetype(p, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


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


# ONNX sessions are cached per model path. A single mutable backend would race
# when two cameras select different models concurrently.
_onnx_backends: dict[str, OnnxBackend] = {}
_onnx_backends_lock = threading.Lock()
_model_state_lock = threading.Lock()
_model_state = {
    "status": "idle",
    "model": "",
    "error": "",
}


def _get_onnx_backend(weights_path: str) -> OnnxBackend:
    with _onnx_backends_lock:
        backend = _onnx_backends.get(weights_path)
        if backend is None:
            backend = OnnxBackend()
            _onnx_backends[weights_path] = backend
        return backend


def _resolve_weights_path(model: str = "") -> str:
    weights_path = model or _find_default_weights() or ""
    if not weights_path:
        raise HTTPException(503, "No inference model is available")
    try:
        return _validate_weights_path(weights_path)
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _set_model_state(status: str, model: str = "", error: str = "") -> None:
    with _model_state_lock:
        _model_state.update({"status": status, "model": model, "error": error})


def _get_model_state() -> dict:
    with _model_state_lock:
        return dict(_model_state)


def _preload_model_worker(weights_path: str) -> None:
    _set_model_state("loading", weights_path)
    try:
        if _is_onnx_model(weights_path):
            _get_onnx_backend(weights_path)._load_model(weights_path)
        else:
            preload_model(weights_path)
    except Exception as exc:
        logger.exception("Model preload failed: %s", weights_path)
        _set_model_state("error", weights_path, str(exc))
    else:
        _set_model_state("ready", weights_path)


def _build_inference_backend(weights_path: str):
    if _is_onnx_model(weights_path):
        return _get_onnx_backend(weights_path)
    return build_backend("ultralytics")


def _load_class_names() -> dict[int, str]:
    """Load class_id -> class_name mapping from classes.yaml."""
    if not CLASS_CONFIG.exists():
        return {}
    data = load_yaml(str(CLASS_CONFIG))
    classes = data.get("classes", [])
    return {i: str(name) for i, name in enumerate(classes)}


def _onnx_detections_to_detection_outs(
    results: list[dict],
    display_names: dict[str, str],
    class_names: dict[int, str],
) -> list[DetectionOut]:
    """Convert OnnxBackend.predict_frame() results to DetectionOut list."""
    detections: list[DetectionOut] = []
    for r in results:
        class_id = r["class_id"]
        class_name = class_names.get(class_id, str(class_id))
        detections.append(DetectionOut(
            xyxy=r["xyxy"],
            confidence=round(r["confidence"], 4),
            class_id=class_id,
            class_name=class_name,
            display_name=display_names.get(class_name, class_name),
        ))
    return detections


def _infer_frame_detections(
    frame: np.ndarray,
    weights_path: str,
    confidence: float,
    iou: float,
) -> list[DetectionOut]:
    display_names = _load_class_display_names()
    if _is_onnx_model(weights_path):
        backend = _get_onnx_backend(weights_path)
        results = backend.predict_frame(frame, weights_path, confidence, iou)
        return _onnx_detections_to_detection_outs(
            results, display_names, _load_class_names()
        )

    model = get_model(weights_path)
    results = model.predict(
        source=frame,
        conf=confidence,
        iou=iou,
        verbose=False,
        stream=False,
        save=False,
    )
    if not results:
        return []
    return _extract_detections(results[0], display_names)


async def _infer_frame_for_request(
    frame: np.ndarray,
    model: str,
    confidence: float,
    iou: float,
) -> list[DetectionOut]:
    weights_path = _resolve_weights_path(model)
    try:
        return await asyncio.to_thread(
            _infer_frame_detections,
            frame,
            weights_path,
            confidence,
            iou,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Inference failed with model %s", weights_path)
        raise HTTPException(500, f"Inference failed: {exc}") from exc


def _draw_detection_outs(
    image: np.ndarray,
    detections: list[DetectionOut],
) -> np.ndarray:
    pil_img = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    font = _get_font(18)
    colors = [(56, 189, 248), (244, 114, 182), (52, 211, 153), (251, 191, 36)]
    for detection in detections:
        x1, y1, x2, y2 = [int(value) for value in detection.xyxy]
        color = colors[detection.class_id % len(colors)]
        label = f"{detection.display_name or detection.class_name} {detection.confidence:.2f}"
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
        bbox = draw.textbbox((0, 0), label, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        label_top = max(0, y1 - text_height - 8)
        draw.rectangle(
            [x1, label_top, x1 + text_width + 8, label_top + text_height + 8],
            fill=color,
        )
        draw.text((x1 + 4, label_top + 4), label, fill=(0, 0, 0), font=font)
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the server first; model loading happens in a daemon thread so the
    # loading screen and health endpoint are available immediately.
    default_weights = _find_startup_weights()
    if default_weights:
        threading.Thread(
            target=_preload_model_worker,
            args=(default_weights,),
            daemon=True,
            name="insightclass-model-preload",
        ).start()
    ping_task = asyncio.create_task(_ping_cameras_periodically())
    try:
        yield
    finally:
        ping_task.cancel()
        _stream_registry.stop_all()
        _clear_batch_jobs()
        with _onnx_backends_lock:
            _onnx_backends.clear()
        clear_cache()


app = FastAPI(title="InsightClass Web", lifespan=lifespan)

if _FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="static-assets")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/experiments")
async def list_experiments():
    return JSONResponse(_get_experiments())


@app.get("/api/system/status")
async def system_status():
    return JSONResponse({"service": "ready", "model": _get_model_state()})


def _experiment_artifact_path(exp_id: str, filename: str) -> Path:
    root = EXPERIMENTS_ROOT.resolve()
    candidate = (root / exp_id / filename).resolve()
    if root not in candidate.parents:
        raise HTTPException(400, "Invalid experiment id")
    return candidate


@app.get("/api/experiments/{exp_id}/results.csv")
async def get_results_csv(exp_id: str):
    csv_path = _experiment_artifact_path(exp_id, "results.csv")
    if not csv_path.exists():
        raise HTTPException(404, "results.csv not found")
    text = csv_path.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    return JSONResponse({"columns": reader.fieldnames or [], "rows": rows})


@app.get("/api/experiments/{exp_id}/confusion_matrix")
async def get_confusion_matrix(exp_id: str):
    img_path = _experiment_artifact_path(exp_id, "confusion_matrix.png")
    if not img_path.exists():
        raise HTTPException(404, "confusion_matrix.png not found")
    return FileResponse(img_path, media_type="image/png")


@app.get("/api/experiments/{exp_id}/results.png")
async def get_results_png(exp_id: str):
    img_path = _experiment_artifact_path(exp_id, "results.png")
    if not img_path.exists():
        raise HTTPException(404, "results.png not found")
    return FileResponse(img_path, media_type="image/png")


@app.get("/api/settings/default-model")
async def get_default_model():
    return JSONResponse({"model": _get_default_model()})


@app.post("/api/settings/default-model")
async def set_default_model(request: Request):
    body = await request.json()
    model = _resolve_weights_path(str(body.get("model", "")))
    _update_app_config({"default_model": model})
    threading.Thread(
        target=_preload_model_worker,
        args=(model,),
        daemon=True,
        name="insightclass-model-preload",
    ).start()
    return JSONResponse({"ok": True, "model": model})


@app.get("/api/settings/display-names")
async def get_display_names():
    return JSONResponse(_load_class_display_names())


@app.get("/api/settings/ui-defaults")
async def get_ui_defaults():
    experiments = _get_experiments()
    saved_model = _get_default_model()
    if not saved_model and experiments:
        saved_model = experiments[0].get("weights_path", "")
    return JSONResponse({
        "model": saved_model,
        "confidence": DEFAULT_CONFIDENCE,
        "iou": DEFAULT_IOU,
    })


@app.get("/api/settings/llm")
async def get_llm_settings():
    return JSONResponse(_public_llm_config())


@app.post("/api/settings/llm")
async def set_llm_settings(request: Request):
    body = await request.json()
    current = _load_app_config().get("llm", {})
    if not isinstance(current, dict):
        current = {}
    api_key = body.get("api_key")
    if body.get("clear_api_key"):
        api_key = ""
    elif api_key is None or not str(api_key).strip():
        api_key = current.get("api_key", "")
    try:
        config = OpenAICompatibleConfig(
            base_url=str(body.get("base_url", current.get("base_url", DEFAULT_LLM_BASE_URL))),
            model=str(body.get("model", current.get("model", ""))),
            api_key=str(api_key),
            timeout=float(body.get("timeout", current.get("timeout", 60))),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    _update_app_config({
        "llm": {
            "base_url": config.base_url,
            "model": config.model,
            "api_key": config.api_key,
            "timeout": config.timeout,
        }
    })
    return JSONResponse(_public_llm_config())


@app.post("/api/llm/test")
async def test_llm_connection():
    client = _build_llm_client()
    try:
        result = await asyncio.to_thread(
            client.chat,
            [{
                "role": "user",
                "content": "Reply with the single word OK.",
            }],
            temperature=0,
            max_tokens=8,
        )
    except LlmClientError as exc:
        raise HTTPException(502, str(exc)) from exc
    return JSONResponse({"ok": True, "model": result["model"], "preview": result["content"][:200]})


@app.post("/api/llm/analyze")
async def analyze_with_llm(request: Request):
    body = await request.json()
    prompt = str(body.get("prompt", "")).strip()
    if not prompt:
        raise HTTPException(422, "Prompt is required")
    if len(prompt) > 4000:
        raise HTTPException(413, "Prompt is too long")
    context = body.get("context", {})
    try:
        context_text = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "Context must be JSON serializable") from exc
    if len(context_text) > 20000:
        raise HTTPException(413, "Analysis context is too large")

    client = _build_llm_client()
    messages = [
        {
            "role": "system",
            "content": (
                "你是课堂行为检测分析助手。只能根据提供的统计数据回答，"
                "不要编造未提供的事实；用简洁、可执行的中文给出结论和建议。"
            ),
        },
        {
            "role": "user",
            "content": f"{prompt}\n\n统计数据(JSON):\n{context_text}",
        },
    ]
    try:
        result = await asyncio.to_thread(
            client.chat, messages, temperature=0.2, max_tokens=800
        )
    except LlmClientError as exc:
        raise HTTPException(502, str(exc)) from exc
    return JSONResponse({
        "analysis": result["content"],
        "model": result["model"],
        "usage": result.get("usage", {}),
    })


@app.post("/api/detect/frame")
async def detect_frame(
    image: UploadFile = File(...),
    model: str = Form(default=""),
    confidence: float = Form(default=DEFAULT_CONFIDENCE, ge=0.0, le=1.0),
    iou: float = Form(default=DEFAULT_IOU, ge=0.0, le=1.0),
):
    t0 = time.time()
    _validate_upload_suffix(image, IMAGE_SUFFIXES, "image")
    contents = await _read_upload_limited(image, MAX_IMAGE_UPLOAD_BYTES, "Image")
    frame = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(400, "Unable to decode image")
    h, w = frame.shape[:2]
    if h * w > MAX_IMAGE_PIXELS:
        raise HTTPException(413, "Decoded image dimensions are too large")
    detections = await _infer_frame_for_request(
        frame, model, confidence, iou
    )

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
    confidence: float = Form(default=DEFAULT_CONFIDENCE, ge=0.0, le=1.0),
    iou: float = Form(default=DEFAULT_IOU, ge=0.0, le=1.0),
):
    t0 = time.time()

    suffix = _validate_upload_suffix(video, VIDEO_SUFFIXES, "video")
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / f"video{suffix}"
        await _write_upload_limited(video, tmp_path, MAX_VIDEO_UPLOAD_BYTES, "Video")
        weights_path = _resolve_weights_path(model)

        cap = cv2.VideoCapture(str(tmp_path))
        if not cap.isOpened():
            cap.release()
            raise HTTPException(400, "Unable to open uploaded video")
        video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        config = InferenceConfig(
            backend="onnx" if _is_onnx_model(weights_path) else "ultralytics",
            weights_path=weights_path,
            source=str(tmp_path),
            output_dir=str(Path(tmp_dir) / "output"),
            confidence=confidence,
            iou=iou,
            device="cpu",
            save_frames=False,
            save_video=False,
            class_names=list(_load_class_names().values()),
        )
        backend = _build_inference_backend(weights_path)
        predictions = await asyncio.to_thread(
            backend.load_predictions_as_sv_detections, config
        )

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


@app.post("/api/detect/image")
async def detect_image(
    image: UploadFile = File(...),
    model: str = Form(default=""),
    confidence: float = Form(default=DEFAULT_CONFIDENCE, ge=0.0, le=1.0),
    iou: float = Form(default=DEFAULT_IOU, ge=0.0, le=1.0),
):
    t0 = time.time()
    _validate_upload_suffix(image, IMAGE_SUFFIXES, "image")
    contents = await _read_upload_limited(image, MAX_IMAGE_UPLOAD_BYTES, "Image")
    img = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "Unable to decode image")
    if img.shape[0] * img.shape[1] > MAX_IMAGE_PIXELS:
        raise HTTPException(413, "Decoded image dimensions are too large")

    detections = await _infer_frame_for_request(img, model, confidence, iou)
    annotated = await asyncio.to_thread(_draw_detection_outs, img, detections)
    encoded, buf = cv2.imencode(
        ".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 92]
    )
    if not encoded:
        raise HTTPException(500, "Unable to encode detection result")
    img_b64 = base64.b64encode(buf).decode("ascii")

    latency = round((time.time() - t0) * 1000, 1)
    return JSONResponse({
        "image": f"data:image/jpeg;base64,{img_b64}",
        "detections": [item.model_dump() for item in detections],
        "latency_ms": latency,
    })


# ---- Batch Video Detection ----

@app.post("/api/detect/batch-upload")
async def batch_upload(videos: list[UploadFile] = File(...)):
    if not videos:
        raise HTTPException(400, "At least one video is required")
    if len(videos) > MAX_BATCH_FILES:
        raise HTTPException(413, f"A batch can contain at most {MAX_BATCH_FILES} videos")
    batch_id = uuid.uuid4().hex[:12]
    tmp_dir = tempfile.mkdtemp(prefix="ic_batch_")
    items: list[dict] = []
    total_bytes = 0
    try:
        for idx, video in enumerate(videos):
            suffix = _validate_upload_suffix(video, VIDEO_SUFFIXES, "video")
            display_name = Path(video.filename).name if video.filename else f"video{suffix}"
            tmp_path = Path(tmp_dir) / f"video_{idx}{suffix}"
            remaining = MAX_BATCH_UPLOAD_BYTES - total_bytes
            if remaining <= 0:
                raise HTTPException(413, "Batch upload exceeds the total size limit")
            written = await _write_upload_limited(
                video,
                tmp_path,
                min(MAX_VIDEO_UPLOAD_BYTES, remaining),
                f"Video {idx + 1}",
            )
            total_bytes += written
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
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    job = {
        "batch_id": batch_id,
        "status": "pending",
        "items": items,
        "total_latency_sec": 0,
        "_dir": tmp_dir,
    }
    with _batch_jobs_lock:
        _batch_jobs[batch_id] = job
    return JSONResponse({
        "batch_id": batch_id,
        "status": "pending",
        "item_count": len(items),
    })


@app.post("/api/detect/batch/{batch_id}")
async def batch_detect(
    batch_id: str,
    model: str = Form(default=""),
    confidence: float = Form(default=DEFAULT_CONFIDENCE, ge=0.0, le=1.0),
    iou: float = Form(default=DEFAULT_IOU, ge=0.0, le=1.0),
):
    with _batch_jobs_lock:
        job = _batch_jobs.get(batch_id)
        if not job:
            return JSONResponse({"error": "Batch not found"}, status_code=404)
        if job["status"] != "pending":
            return JSONResponse({"error": "Batch detection has already started"}, status_code=409)

    weights_path = _resolve_weights_path(model)
    with _batch_jobs_lock:
        job = _batch_jobs.get(batch_id)
        if not job:
            return JSONResponse({"error": "Batch not found"}, status_code=404)
        if job["status"] != "pending":
            return JSONResponse({"error": "Batch detection has already started"}, status_code=409)
        job["status"] = "processing"
        job["_weights_path"] = weights_path
        job["_confidence"] = confidence
        job["_iou"] = iou

    # Start background processing
    thread = threading.Thread(target=_batch_detect_worker, args=(job,), daemon=True)
    thread.start()

    return JSONResponse({"ok": True, "status": "processing"})


def _schedule_batch_cleanup(batch_id: str, delay_sec: int = 3600):
    """Remove batch job and its temp dir after delay."""
    def _cleanup():
        time.sleep(delay_sec)
        with _batch_jobs_lock:
            job = _batch_jobs.pop(batch_id, None)
        if job:
            tmp_dir = job.get("_dir")
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)
    threading.Thread(target=_cleanup, daemon=True).start()


def _batch_detect_worker(job: dict):
    """Background worker for batch detection — runs sequentially, updates status per item."""
    weights_path = job["_weights_path"]
    confidence = job["_confidence"]
    iou = job["_iou"]

    t0 = time.time()
    try:
        display_names = _load_class_display_names()
        backend = _build_inference_backend(weights_path)
    except Exception as exc:
        for item in job["items"]:
            item["status"] = "error"
            item["error"] = str(exc)
        job["status"] = "error"
        job["total_latency_sec"] = round(time.time() - t0, 2)
        _schedule_batch_cleanup(job["batch_id"])
        return

    for i, item in enumerate(job["items"]):
        item["status"] = "processing"
        item["_index"] = i
        try:
            video_path = item["_path"]
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                cap.release()
                raise ValueError("Unable to open uploaded video")
            item["fps"] = round(cap.get(cv2.CAP_PROP_FPS) or 30.0, 2)
            item["video_width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            item["video_height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            item["frame_count"] = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()

            t1 = time.time()
            config = InferenceConfig(
                backend="onnx" if _is_onnx_model(weights_path) else "ultralytics",
                weights_path=weights_path,
                source=video_path,
                output_dir=os.path.join(job["_dir"], "output"),
                confidence=confidence,
                iou=iou,
                device="cpu",
                save_frames=False,
                save_video=False,
                class_names=list(_load_class_names().values()),
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

    job["status"] = "error" if any(item["status"] == "error" for item in job["items"]) else "done"
    job["total_latency_sec"] = round(time.time() - t0, 2)
    _schedule_batch_cleanup(job["batch_id"])


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
    """构建摄像头列表（从 cameras.yaml 读取）。"""
    custom_cameras = _load_custom_cameras()
    creds = _get_rtsp_credentials()
    with _camera_ping_lock:
        ping_results = dict(_camera_ping_results)

    cameras = []
    for cam in custom_cameras:
        try:
            ip = _validate_camera_ip(str(cam.get("ip", "")))
        except ValueError:
            logger.warning("Skipping invalid camera IP in config: %s", cam.get("ip"))
            continue
        if not ip:
            continue
        entry = {
            "ip": ip,
            "name": cam.get("name", ""),
            "group": cam.get("group", "custom"),
            "group_label": cam.get("group_label", "自定义"),
            "note": cam.get("note", ""),
            "custom": True,
            "_status": (
                "connected" if _stream_registry.is_active(ip)
                else (
                    "unknown" if ip not in ping_results
                    else ("online" if ping_results[ip].get("reachable") else "offline")
                )
            ),
        }
        if include_credentials:
            entry["username"] = creds["username"]
            entry["password"] = creds["password"]
            entry["port"] = creds["port"]
        cameras.append(entry)
    return cameras


@app.get("/api/cameras")
async def list_cameras():
    return JSONResponse(content=_build_camera_list(), media_type="application/json; charset=utf-8")


@app.post("/api/cameras")
async def add_camera(request: Request):
    body = await request.json()
    try:
        ip = _validate_camera_ip(body.get("ip", ""))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    if not ip:
        return JSONResponse({"error": "IP is required"}, status_code=400)
    cameras = _load_custom_cameras()
    if any(c["ip"] == ip for c in cameras):
        return JSONResponse({"error": f"Camera {ip} already exists"}, status_code=409)
    cam = {
        "ip": ip,
        "name": body.get("name", "").strip(),
        "group": body.get("group", "custom"),
        "group_label": body.get("group_label", "自定义"),
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

    if idx is not None:
        cameras[idx].update({
            "name": body.get("name", cameras[idx].get("name", "")),
            "group": body.get("group", cameras[idx].get("group", "custom")),
            "group_label": body.get("group_label", cameras[idx].get("group_label", "自定义")),
            "note": body.get("note", cameras[idx].get("note", "")),
        })
    else:
        return JSONResponse({"error": "Camera not found"}, status_code=404)

    _save_custom_cameras(cameras)
    return JSONResponse({"ok": True}, media_type="application/json; charset=utf-8")


@app.delete("/api/cameras/{ip}")
async def delete_camera(ip: str):
    normalized_ip = _require_camera_ip(ip)
    cameras = _load_custom_cameras()
    if not any(c.get("ip") == normalized_ip for c in cameras):
        return JSONResponse({"error": "Camera not found"}, status_code=404)
    cameras = [c for c in cameras if c.get("ip") != normalized_ip]
    _save_custom_cameras(cameras)
    _stream_registry.stop(normalized_ip)
    _dashboard_stats.remove(normalized_ip)
    return JSONResponse({"ok": True}, media_type="application/json; charset=utf-8")


@app.get("/api/cameras/{ip}/test")
async def test_single_camera(ip: str):
    """Test connectivity for a single camera, return result immediately."""
    cameras = _build_camera_list(include_credentials=True)
    cam = next((c for c in cameras if c["ip"] == ip), None)
    if not cam:
        return JSONResponse({"error": "Camera not found"}, status_code=404)
    rtsp_url = _build_rtsp_url(ip)
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
            ip = _validate_camera_ip(cam["ip"])
            rtsp_url = _build_rtsp_url(ip)
        else:
            ip = _validate_camera_ip(str(cam))
            rtsp_url = _build_rtsp_url(ip)
        ok = await asyncio.to_thread(_test_camera_connection, rtsp_url)
        return ip, "connected" if ok else "disconnected"

    results_list = await asyncio.gather(*[_test_one(cam) for cam in camera_list])
    return JSONResponse(dict(results_list), media_type="application/json; charset=utf-8")


def _test_camera_connection(rtsp_url: str) -> bool:
    try:
        with _rtsp_lock:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = _FFMPEG_OPTIONS
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            return False
        ret, frame = cap.read()
        cap.release()
        return ret and frame is not None
    except Exception:
        return False


@app.get("/api/stream/rtsp")
async def stream_rtsp(request: Request, camera_ip: str):
    """MJPEG stream for one configured camera."""
    normalized_ip = _require_camera_ip(camera_ip)
    rtsp_url = _resolve_camera_rtsp_url(normalized_ip)
    manager = _stream_registry.start(normalized_ip, rtsp_url)

    async def generate():
        try:
            while manager.get_status()["active"] or manager.get_status()["status"] == "connecting":
                if await request.is_disconnected():
                    break
                frame = manager.get_frame()
                if frame:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                    )
                else:
                    await asyncio.sleep(0.05)
        finally:
            # The manager is shared with the detection endpoint. Stopping it
            # here would make a browser tab disconnect the detector.
            pass

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@app.post("/api/stream/stop")
async def stream_stop(camera_ip: str = ""):
    if camera_ip:
        _stream_registry.stop(_require_camera_ip(camera_ip))
    else:
        _stream_registry.stop_all()
    return JSONResponse({"ok": True})


@app.get("/api/stream/status")
async def stream_status(camera_ip: str):
    normalized_ip = _require_camera_ip(camera_ip)
    return JSONResponse(_stream_registry.get_status(normalized_ip))


@app.post("/api/detect/rtsp")
async def detect_rtsp(
    camera_ip: str = Form(...),
    model: str = Form(default=""),
    confidence: float = Form(default=DEFAULT_CONFIDENCE, ge=0.0, le=1.0),
    iou: float = Form(default=DEFAULT_IOU, ge=0.0, le=1.0),
):
    t0 = time.time()

    normalized_ip = _require_camera_ip(camera_ip)
    rtsp_url = _resolve_camera_rtsp_url(normalized_ip)
    # Ensure this camera's stream is running.
    manager = _stream_registry.start(normalized_ip, rtsp_url)

    # Grab the latest frame from the persistent stream
    frame_bytes = manager.get_frame()
    if not frame_bytes:
        return FrameDetectionResponse(detections=[], latency_ms=0, frame_width=0, frame_height=0)

    # Decode frame for YOLO inference
    arr = np.frombuffer(frame_bytes, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        return FrameDetectionResponse(detections=[], latency_ms=0, frame_width=0, frame_height=0)

    h, w = frame.shape[:2]
    detections = await _infer_frame_for_request(frame, model, confidence, iou)

    # Record dashboard stats
    for det in detections:
        _dashboard_stats.record(normalized_ip, det.class_name)

    latency = (time.time() - t0) * 1000
    return FrameDetectionResponse(
        detections=detections,
        latency_ms=round(latency, 1),
        frame_width=int(w),
        frame_height=int(h),
    )


@app.get("/api/dashboard/stats")
async def dashboard_stats():
    raw = _dashboard_stats.get_all()
    cameras = _build_camera_list()
    # Build a lookup from raw stats by IP
    stats_by_ip = {c["ip"]: c for c in raw["cameras"]}
    result_cameras = []
    total = {"phone_use": 0, "talking": 0, "sleeping": 0, "standing": 0}
    for cam in cameras:
        ip = cam["ip"]
        data = stats_by_ip.get(ip, {"stats": {"phone_use": 0, "talking": 0, "sleeping": 0, "standing": 0}, "last_update": None})
        camera_status = cam.get("_status", "unknown")
        result_cameras.append({
            "ip": ip,
            "name": cam.get("name") or cam.get("group_label", ""),
            "group": cam.get("group", "custom"),
            "group_label": cam.get("group_label", "自定义"),
            "online": camera_status in ("connected", "online"),
            "status": camera_status,
            "stats": data["stats"],
            "last_update": data["last_update"],
        })
        for class_name in total:
            total[class_name] += data["stats"].get(class_name, 0)
    return JSONResponse({
        "cameras": result_cameras,
        "total": total,
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
    """Return real in-memory hourly counts for the last 24 hours."""
    camera_ips = [camera["ip"] for camera in _build_camera_list()]
    history = _dashboard_stats.get_history(camera_ips)
    return JSONResponse({"history": history, "simulated": False})


# ---- Global RTSP Credentials ----

@app.get("/api/settings/rtsp-credentials")
async def get_rtsp_credentials():
    """Return RTSP settings without exposing the stored password."""
    creds = _get_rtsp_credentials()
    password = str(creds.get("password", ""))
    return JSONResponse({
        "username": creds.get("username", DEFAULT_RTSP_USERNAME),
        "password": "",
        "has_password": bool(password),
        "password_masked": f"...{password[-4:]}" if password else "",
        "port": creds.get("port", DEFAULT_RTSP_PORT),
    })


@app.post("/api/settings/rtsp-credentials")
async def set_rtsp_credentials(request: Request):
    """设置全局 RTSP 凭据。"""
    body = await request.json()
    current = _get_rtsp_credentials()
    password = body.get("password")
    if password is None or not str(password).strip():
        password = current["password"]
    rtsp_credentials = {
        "username": str(body.get("username", current["username"])).strip() or current["username"],
        "password": str(password),
        "port": body.get("port", current["port"]),
    }

    try:
        port = int(rtsp_credentials["port"])
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "RTSP port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise HTTPException(422, "RTSP port must be between 1 and 65535")
    rtsp_credentials["port"] = port
    _update_app_config({"rtsp_credentials": rtsp_credentials})
    _stream_registry.stop_all()
    return JSONResponse({"ok": True})


def _get_llm_config() -> dict:
    cfg = _load_app_config().get("llm", {})
    if not isinstance(cfg, dict):
        cfg = {}
    return {
        "base_url": os.getenv("OPENAI_BASE_URL", cfg.get("base_url", DEFAULT_LLM_BASE_URL)),
        "model": os.getenv("OPENAI_MODEL", cfg.get("model", "")),
        "api_key": os.getenv("OPENAI_API_KEY", cfg.get("api_key", "")),
        "timeout": float(cfg.get("timeout", 60)),
    }


def _public_llm_config() -> dict:
    config = _get_llm_config()
    key = str(config.get("api_key", ""))
    return {
        "base_url": config["base_url"],
        "model": config["model"],
        "timeout": config["timeout"],
        "has_api_key": bool(key),
        "api_key_masked": f"...{key[-4:]}" if key else "",
    }


def _build_llm_client() -> OpenAICompatibleClient:
    config = _get_llm_config()
    try:
        return OpenAICompatibleClient(OpenAICompatibleConfig(**config))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


# ---- CSV Import Cameras ----

def _detect_csv_columns(header: list[str]) -> dict[str, int]:
    """Auto-detect column indices from a CSV header row.

    Returns a dict mapping field names to column indices.
    Supported fields: ip, name, and username.
    Falls back to Hikvision default column positions when header
    matching fails.
    """
    col_map: dict[str, int] = {}

    # Normalize header for matching
    normalized = [c.strip().lower() for c in header]

    # IP address
    for i, col in enumerate(normalized):
        if col in ('ip地址', 'ip', 'ip地址', 'ip地址'):
            col_map['ip'] = i
            break
    if 'ip' not in col_map and len(header) >= 1:
        # Hikvision default: column 0 is IP
        col_map['ip'] = 0

    # Device name (serial number or alias)
    for i, col in enumerate(normalized):
        if col in ('设备序列号', '序列号', '设备名称', '设备别名', '别名', '名称'):
            col_map['name'] = i
            break
    if 'name' not in col_map and len(header) >= 5:
        # Hikvision default: column 4 is device serial number
        col_map['name'] = 4

    # Username
    for i, col in enumerate(normalized):
        if col in ('用户名', 'username', '登录用户名', '用户'):
            col_map['username'] = i
            break
    if 'username' not in col_map and len(header) >= 6:
        # Hikvision default: column 5 is username
        col_map['username'] = 5

    return col_map


@app.post("/api/cameras/import")
async def import_cameras_csv(file: UploadFile = File(...)):
    """上传 CSV 文件批量导入摄像头（支持海康威视导出格式）。

    CSV 格式（GB2312/GBK 编码）：
    - Column 0: IP address
    - Column 3: Port (HTTP management port, 8000)
    - Column 4: Device serial number (used as device name)
    - Column 5: Username
    Password columns are intentionally ignored; configure the shared RTSP
    password in the settings screen instead.
    """
    try:
        if Path(file.filename or "").suffix.lower() != ".csv":
            raise HTTPException(415, "Only CSV files are supported")
        contents = await _read_upload_limited(file, MAX_CSV_UPLOAD_BYTES, "CSV file")

        # Try multiple encodings
        text = None
        for encoding in ['gb18030', 'gbk', 'gb2312', 'utf-8-sig', 'utf-8']:
            try:
                text = contents.decode(encoding)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if text is None:
            return JSONResponse({"error": "无法解码文件，请确保是 GB2312/GBK/UTF-8 编码的 CSV"}, status_code=400)

        # Parse CSV
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if len(rows) < 2:
            return JSONResponse({"error": "CSV 文件为空或只有表头"}, status_code=400)

        # Auto-detect columns from header
        header = rows[0]
        col_map = _detect_csv_columns(header)

        if 'ip' not in col_map:
            return JSONResponse({"error": "CSV 中找不到 IP 地址列"}, status_code=400)

        ip_col = col_map['ip']
        name_col = col_map.get('name')
        username_col = col_map.get('username')

        existing_cameras = _load_custom_cameras()
        existing_ips = {c["ip"] for c in existing_cameras}
        imported = 0
        skipped = 0
        errors = []

        for row_idx, row in enumerate(rows[1:], start=2):
            if len(row) <= ip_col:
                continue
            ip = row[ip_col].strip()
            if not ip:
                continue
            # Validate IP format
            if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
                errors.append(f"第 {row_idx} 行: 无效 IP '{ip}'")
                continue
            if ip in existing_ips:
                skipped += 1
                continue

            # Extract device name (serial number)
            device_name = ""
            if name_col is not None and len(row) > name_col:
                device_name = row[name_col].strip()

            # Extract username
            username = ""
            if username_col is not None and len(row) > username_col:
                username = row[username_col].strip()

            # Build note with RTSP info (always use port 554, not CSV's HTTP port)
            note_parts = ["RTSP:554"]
            if username:
                note_parts.append(f"用户:{username}")
            note = " ".join(note_parts)

            existing_cameras.append({
                "ip": ip,
                "name": device_name,
                "group": "custom",
                "group_label": "自定义",
                "note": note,
            })
            existing_ips.add(ip)
            imported += 1

        _save_custom_cameras(existing_cameras)
        return JSONResponse({
            "ok": True,
            "imported": imported,
            "skipped": skipped,
            "errors": errors,
            "total_in_csv": len(rows) - 1,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("CSV import failed: %s", e)
        return JSONResponse({"error": f"导入失败: {str(e)}"}, status_code=500)


# ---- SPA Fallback (must be registered LAST) ----

@app.get("/{path:path}")
async def serve_spa(path: str):
    """Serve built React frontend — static files take priority, everything else falls back to index.html."""
    if not _FRONTEND_DIST.exists():
        raise HTTPException(404, "Frontend not built")
    frontend_root = _FRONTEND_DIST.resolve()
    file_path = (frontend_root / path).resolve()
    if frontend_root not in file_path.parents and file_path != frontend_root:
        raise HTTPException(404, "Frontend file not found")
    if file_path.is_file():
        return FileResponse(file_path)
    index_path = frontend_root / "index.html"
    if not index_path.is_file():
        raise HTTPException(404, "Frontend not built")
    return FileResponse(index_path)
