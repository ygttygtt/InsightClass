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
        self._input_name = self._session.get_inputs()[0].name
        self._model_path = weights_path

    # ------------------------------------------------------------------
    # Pre / post processing
    # ------------------------------------------------------------------

    @staticmethod
    def _preprocess(
        img: np.ndarray, imgsz: int = 960
    ) -> tuple[np.ndarray, tuple[float, float]]:
        """Resize, pad and normalize image for YOLO input.

        Returns (blob, (ratio, ratio)) where blob shape is (1, 3, imgsz, imgsz).
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
        return np.expand_dims(img, 0), (r, r)

    @staticmethod
    def _postprocess(
        output: np.ndarray,
        ratio: tuple[float, float],
        conf_threshold: float,
        iou_threshold: float,
    ) -> list[dict]:
        """Parse YOLO output tensor into detections with NMS.

        Args:
            output: Raw ONNX output, shape (1, 4+num_classes, num_boxes).
            ratio: Preprocessing scale ratio (currently unused; boxes are in
                model-input coordinates).
            conf_threshold: Minimum confidence to keep a detection.
            iou_threshold: IoU threshold for non-maximum suppression.

        Returns:
            List of dicts with keys ``xyxy``, ``confidence``, ``class_id``.
        """
        # (1, 4+nc, N) -> (N, 4+nc)
        preds = output[0].T

        boxes = preds[:, :4]  # cx, cy, w, h
        scores = preds[:, 4:]  # class scores

        max_scores = scores.max(axis=1)
        class_ids = scores.argmax(axis=1)

        mask = max_scores > conf_threshold
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
        xyxy = np.stack([x1, y1, x2, y2], axis=1)

        # NMS via OpenCV DNN module
        indices = cv2.dnn.NMSBoxes(
            xyxy.tolist(), max_scores.tolist(),
            conf_threshold, iou_threshold,
        )
        if len(indices) == 0:
            return []
        indices = indices.flatten()

        results: list[dict] = []
        for i in indices:
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
        imgsz: int = 960,
    ) -> list[dict]:
        """Run inference on a single frame.

        Returns a list of dicts with keys ``xyxy``, ``confidence``, ``class_id``.
        """
        self._load_model(weights_path)
        blob, ratio = self._preprocess(frame, imgsz)
        output = self._session.run(None, {self._input_name: blob})[0]
        return self._postprocess(output, ratio, confidence, iou)

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
