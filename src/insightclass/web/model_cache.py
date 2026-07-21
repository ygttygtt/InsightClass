from __future__ import annotations

from insightclass.optional import require_package

_model_cache: dict[str, object] = {}


def _is_onnx_model(weights_path: str) -> bool:
    return weights_path.lower().endswith(".onnx")


def get_model(weights_path: str):
    path = str(weights_path)

    if path not in _model_cache:
        if _is_onnx_model(path):
            require_package("onnxruntime", "ONNX inference")
            import onnxruntime as ort
            _model_cache[path] = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        else:
            require_package("ultralytics", "Web inference")
            from ultralytics import YOLO
            _model_cache[path] = YOLO(path)

    return _model_cache[path]


def preload_model(weights_path: str) -> None:
    get_model(weights_path)


def clear_cache() -> None:
    _model_cache.clear()
