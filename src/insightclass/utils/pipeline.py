from __future__ import annotations

from pathlib import Path

from insightclass.backends.ultralytics_backend import UltralyticsBackend
from insightclass.optional import require_package
from insightclass.schemas import FramePrediction
from insightclass.utils.paths import ensure_dir


class VisualizationPipeline:
    """Render prediction results using supervision annotations."""

    def __init__(self, backend: UltralyticsBackend | None = None) -> None:
        self.backend = backend or UltralyticsBackend()

    def render_image(self, image_path: str, frame_prediction: FramePrediction, output_path: str) -> Path:
        require_package("supervision", "Visualization pipeline")
        require_package("cv2", "Visualization pipeline")
        import cv2
        import supervision as sv

        image = cv2.imread(image_path)
        if image is None:
            raise FileNotFoundError(f"Unable to load image: {image_path}")
        detections = self.backend.to_supervision_detections(frame_prediction)
        labels = [
            f"{detection.class_name} {detection.confidence:.2f}"
            for detection in frame_prediction.detections
        ]
        box_annotator = sv.BoxAnnotator()
        label_annotator = sv.LabelAnnotator()
        annotated = box_annotator.annotate(scene=image.copy(), detections=detections)
        annotated = label_annotator.annotate(scene=annotated, detections=detections, labels=labels)
        target = Path(output_path)
        ensure_dir(target.parent)
        cv2.imwrite(str(target), annotated)
        return target

    def render_video_first_frame(self, video_path: str, frame_prediction: FramePrediction, output_path: str) -> Path:
        require_package("supervision", "Visualization pipeline")
        require_package("cv2", "Visualization pipeline")
        import cv2
        import supervision as sv

        capture = cv2.VideoCapture(video_path)
        ok, frame = capture.read()
        capture.release()
        if not ok or frame is None:
            raise RuntimeError(f"Unable to read first frame from video: {video_path}")
        detections = self.backend.to_supervision_detections(frame_prediction)
        labels = [
            f"{detection.class_name} {detection.confidence:.2f}"
            for detection in frame_prediction.detections
        ]
        box_annotator = sv.BoxAnnotator()
        label_annotator = sv.LabelAnnotator()
        annotated = box_annotator.annotate(scene=frame.copy(), detections=detections)
        annotated = label_annotator.annotate(scene=annotated, detections=detections, labels=labels)
        target = Path(output_path)
        ensure_dir(target.parent)
        cv2.imwrite(str(target), annotated)
        return target
