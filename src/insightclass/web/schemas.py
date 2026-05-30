from __future__ import annotations

from pydantic import BaseModel


class DetectionOut(BaseModel):
    xyxy: list[float]
    confidence: float
    class_id: int
    class_name: str
    display_name: str = ""


class FrameDetectionResponse(BaseModel):
    detections: list[DetectionOut]
    latency_ms: float
    frame_width: int
    frame_height: int
    frame_image: str = ""  # base64-encoded JPEG, empty if unavailable


class FrameOut(BaseModel):
    frame_index: int
    detections: list[DetectionOut]


class VideoDetectionResponse(BaseModel):
    frames: list[FrameOut]
    frame_count: int
    fps: float
    total_latency_sec: float
    video_width: int
    video_height: int


class ExperimentSummary(BaseModel):
    experiment_id: str
    weights_path: str
    class_names: list[str]
    metrics: dict


class BatchDetectionResult(BaseModel):
    filename: str
    status: str  # pending / processing / done / error
    frames: list[FrameOut] = []
    frame_count: int = 0
    fps: float = 0
    video_width: int = 0
    video_height: int = 0
    latency_sec: float = 0
    error: str = ""
    detection_summary: dict = {}


class BatchJob(BaseModel):
    batch_id: str
    status: str  # processing / done / error
    items: list[BatchDetectionResult]
    total_latency_sec: float = 0
