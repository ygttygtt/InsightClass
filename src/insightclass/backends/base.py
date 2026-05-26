from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from insightclass.schemas import ExperimentRecord, FramePrediction, InferenceConfig, TrainingConfig


class DetectorBackend(ABC):
    name: str

    @abstractmethod
    def train(self, config: TrainingConfig) -> ExperimentRecord:
        raise NotImplementedError

    @abstractmethod
    def validate(self, config: TrainingConfig) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def predict_images_or_video(self, config: InferenceConfig) -> str:
        raise NotImplementedError

    @abstractmethod
    def load_predictions_as_sv_detections(self, config: InferenceConfig) -> list[FramePrediction]:
        raise NotImplementedError

    @abstractmethod
    def export_artifacts(self, experiment_dir: str) -> dict[str, str]:
        raise NotImplementedError
