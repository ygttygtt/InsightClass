from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class DatasetManifest:
    dataset_name: str
    dataset_version: str
    raw_videos_dir: str
    processed_dir: str
    classes: list[str]
    display_names: dict[str, str] = field(default_factory=dict)
    splits: dict[str, list[str]] = field(default_factory=dict)
    video_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TrainingConfig:
    backend: str
    task: str
    data_config_path: str
    model_weights: str
    image_size: int
    epochs: int
    batch_size: int
    device: str
    project_dir: str
    run_name: str
    seed: int = 42
    patience: int = 50
    workers: int = 4
    extra_args: dict[str, Any] = field(default_factory=dict)

    def resolved_project_dir(self) -> Path:
        return Path(self.project_dir).resolve()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InferenceConfig:
    backend: str
    weights_path: str
    source: str
    output_dir: str
    confidence: float = 0.25
    iou: float = 0.45
    image_size: int = 640
    device: str = "cpu"
    save_frames: bool = False
    save_video: bool = True
    class_names: list[str] = field(default_factory=list)
    extra_args: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExperimentRecord:
    experiment_id: str
    backend: str
    model_weights: str
    data_version: str
    class_names: list[str]
    hyperparameters: dict[str, Any]
    metrics: dict[str, Any]
    artifacts: dict[str, str]
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DetectionRecord:
    xyxy: list[float]
    confidence: float
    class_id: int
    class_name: str


@dataclass(slots=True)
class FramePrediction:
    frame_index: int
    source_path: str
    detections: list[DetectionRecord]
