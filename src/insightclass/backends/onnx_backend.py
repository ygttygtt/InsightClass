"""ONNX Runtime inference backend for YOLO models.

CPU-only inference backend for packaged deployment. Training is not supported;
use the ultralytics backend on a GPU server for training, then export to ONNX.
"""
from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from insightclass.backends.base import DetectorBackend
from insightclass.schemas import (
    DetectionRecord,
    ExperimentRecord,
    FramePrediction,
    InferenceConfig,
    TrainingConfig,
)


class OnnxBackend(DetectorBackend):
    """Lightweight ONNX Runtime backend for single-frame YOLO inference."""

    name = "onnx"

    def __init__(self) -> None:
        self._session: Any | None = None
        self._input_name: str | None = None
        self._model_path: str | None = None
        self._input_size: int | None = None

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_model(self, weights_path: str) -> None:
        """Load ONNX model lazily (cached by path)."""
        if self._model_path == weights_path and self._session is not None:
            return
        import onnxruntime as ort

        self._session = ort.InferenceSession(
            weights_path,
            providers=["CPUExecutionProvider"],
        )
        model_input = self._session.get_inputs()[0]
        self._input_name = model_input.name
        input_width = model_input.shape[-1]
        self._input_size = input_width if isinstance(input_width, int) else None
        self._model_path = weights_path

    # ------------------------------------------------------------------
    # Pre / post processing
    # ------------------------------------------------------------------

    @staticmethod
    def _preprocess(
        img: np.ndarray, imgsz: int = 960
    ) -> tuple[np.ndarray, float, tuple[int, int], tuple[int, int]]:
        """Resize, pad and normalize image for YOLO input.

        Returns the input blob plus the scale, left/top padding and original
        image shape needed to restore detections to source coordinates.
        """
        h, w = img.shape[:2]
        r = imgsz / max(h, w)
        if r != 1:
            img = cv2.resize(
                img, (int(w * r), int(h * r)), interpolation=cv2.INTER_LINEAR
            )

        new_h, new_w = img.shape[:2]
        dw = (imgsz - new_w) / 2
        dh = (imgsz - new_h) / 2
        top = int(round(dh - 0.1))
        bottom = int(round(dh + 0.1))
        left = int(round(dw - 0.1))
        right = int(round(dw + 0.1))
        img = cv2.copyMakeBorder(
            img, top, bottom, left, right,
            cv2.BORDER_CONSTANT, value=(114, 114, 114),
        )

        # HWC -> CHW, BGR -> RGB, normalize to [0, 1]
        img = img[:, :, ::-1].transpose(2, 0, 1).astype(np.float32) / 255.0
        return np.expand_dims(img, 0), r, (left, top), (h, w)

    @staticmethod
    def _postprocess(
        output: np.ndarray,
        scale: float,
        padding: tuple[int, int],
        original_shape: tuple[int, int],
        conf_threshold: float,
        iou_threshold: float,
    ) -> list[dict]:
        """Parse YOLO output tensor into detections with NMS.

        Args:
            output: Raw ONNX output, shape (1, 4+num_classes, num_boxes).
            scale: Scale applied to the original image during preprocessing.
            padding: Left and top padding applied after resizing.
            original_shape: Original image height and width.
            conf_threshold: Minimum confidence to keep a detection.
            iou_threshold: IoU threshold for non-maximum suppression.

        Returns:
            List of dicts with keys ``xyxy``, ``confidence``, ``class_id``.
        """
        preds = output[0]
        # Ultralytics exports (4+classes, boxes). Accept an already transposed
        # (boxes, 4+classes) tensor as well.
        if preds.shape[1] < 5 or preds.shape[0] < preds.shape[1]:
            preds = preds.T

        boxes = preds[:, :4]  # cx, cy, w, h
        scores = preds[:, 4:]  # class scores

        max_scores = scores.max(axis=1)
        class_ids = scores.argmax(axis=1)

        mask = max_scores >= conf_threshold
        boxes = boxes[mask]
        max_scores = max_scores[mask]
        class_ids = class_ids[mask]

        if len(boxes) == 0:
            return []

        # cx,cy,w,h -> x1,y1,x2,y2
        x1 = boxes[:, 0] - boxes[:, 2] / 2
        y1 = boxes[:, 1] - boxes[:, 3] / 2
        x2 = boxes[:, 0] + boxes[:, 2] / 2
        y2 = boxes[:, 1] + boxes[:, 3] / 2
        xyxy = np.stack([x1, y1, x2, y2], axis=1).astype(np.float32)

        # Undo letterbox padding and scale, then clip to the source image.
        pad_x, pad_y = padding
        orig_h, orig_w = original_shape
        xyxy[:, [0, 2]] = (xyxy[:, [0, 2]] - pad_x) / scale
        xyxy[:, [1, 3]] = (xyxy[:, [1, 3]] - pad_y) / scale
        xyxy[:, [0, 2]] = np.clip(xyxy[:, [0, 2]], 0, orig_w)
        xyxy[:, [1, 3]] = np.clip(xyxy[:, [1, 3]], 0, orig_h)

        widths = xyxy[:, 2] - xyxy[:, 0]
        heights = xyxy[:, 3] - xyxy[:, 1]
        valid = (widths > 0) & (heights > 0)
        xyxy = xyxy[valid]
        max_scores = max_scores[valid]
        class_ids = class_ids[valid]
        if len(xyxy) == 0:
            return []

        # OpenCV expects x/y/width/height. Run NMS per class so overlapping
        # detections of different behaviors cannot suppress one another.
        kept: list[int] = []
        for class_id in np.unique(class_ids):
            class_indices = np.flatnonzero(class_ids == class_id)
            class_boxes = xyxy[class_indices]
            nms_boxes = np.column_stack((
                class_boxes[:, 0],
                class_boxes[:, 1],
                class_boxes[:, 2] - class_boxes[:, 0],
                class_boxes[:, 3] - class_boxes[:, 1],
            ))
            selected = cv2.dnn.NMSBoxes(
                nms_boxes.tolist(),
                max_scores[class_indices].tolist(),
                conf_threshold,
                iou_threshold,
            )
            if len(selected):
                kept.extend(class_indices[np.asarray(selected).reshape(-1)].tolist())

        results: list[dict] = []
        for i in sorted(kept, key=lambda idx: float(max_scores[idx]), reverse=True):
            results.append({
                "xyxy": xyxy[i].tolist(),
                "confidence": float(max_scores[i]),
                "class_id": int(class_ids[i]),
            })
        return results

    # ------------------------------------------------------------------
    # Public inference API (single frame)
    # ------------------------------------------------------------------

    def predict_frame(
        self,
        frame: np.ndarray,
        weights_path: str,
        confidence: float = 0.5,
        iou: float = 0.45,
        imgsz: int | None = None,
    ) -> list[dict]:
        """Run inference on a single frame.

        Returns a list of dicts with keys ``xyxy``, ``confidence``, ``class_id``.
        """
        self._load_model(weights_path)
        input_size = imgsz or self._input_size or 960
        blob, scale, padding, original_shape = self._preprocess(frame, input_size)
        output = self._session.run(None, {self._input_name: blob})[0]
        return self._postprocess(
            output,
            scale,
            padding,
            original_shape,
            confidence,
            iou,
        )

    # ------------------------------------------------------------------
    # DetectorBackend ABC stubs (not supported for ONNX)
    # ------------------------------------------------------------------

    def train(self, config: TrainingConfig) -> ExperimentRecord:
        raise NotImplementedError(
            "ONNX backend does not support training. "
            "Use the ultralytics backend on a GPU server."
        )

    def validate(self, config: TrainingConfig) -> dict[str, Any]:
        raise NotImplementedError(
            "ONNX backend does not support validation. "
            "Use the ultralytics backend on a GPU server."
        )

    def predict_images_or_video(self, config: InferenceConfig) -> str:
        raise NotImplementedError(
            "ONNX backend only supports single-frame inference via predict_frame()."
        )

    def load_predictions_as_sv_detections(
        self, config: InferenceConfig
    ) -> list[FramePrediction]:
        raise NotImplementedError(
            "ONNX backend only supports single-frame inference via predict_frame()."
        )

    def export_artifacts(self, experiment_dir: str) -> dict[str, str]:
        raise NotImplementedError(
            "ONNX backend does not produce training artifacts."
        )
