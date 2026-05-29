from __future__ import annotations

from insightclass.optional import require_package

_model_cache: dict[str, object] = {}


def get_model(weights_path: str):
    require_package("ultralytics", "Web inference")
    from ultralytics import YOLO

    path = str(weights_path)
    if path not in _model_cache:
        _model_cache[path] = YOLO(path)
    return _model_cache[path]


def preload_model(weights_path: str) -> None:
    get_model(weights_path)


def clear_cache() -> None:
    _model_cache.clear()
