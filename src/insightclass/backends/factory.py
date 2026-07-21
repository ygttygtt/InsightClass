from __future__ import annotations

from insightclass.backends.base import DetectorBackend


def build_backend(name: str) -> DetectorBackend:
    """Instantiate a backend by name.

    Imports are deferred so that heavy optional dependencies (PyTorch,
    onnxruntime) are only loaded when actually needed.
    """
    normalized = name.strip().lower()
    if normalized in {"ultralytics", "yolo", "ultralytics-yolo"}:
        from insightclass.backends.ultralytics_backend import UltralyticsBackend

        return UltralyticsBackend()
    if normalized in {"onnx"}:
        from insightclass.backends.onnx_backend import OnnxBackend

        return OnnxBackend()
    raise ValueError(f"Unsupported backend: {name}")
