from __future__ import annotations

from insightclass.backends.base import DetectorBackend
from insightclass.backends.ultralytics_backend import UltralyticsBackend


def build_backend(name: str) -> DetectorBackend:
    normalized = name.strip().lower()
    if normalized in {"ultralytics", "yolo", "ultralytics-yolo"}:
        return UltralyticsBackend()
    raise ValueError(f"Unsupported backend: {name}")
