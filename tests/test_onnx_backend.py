import unittest
from unittest.mock import patch

import numpy as np

from insightclass.backends.onnx_backend import OnnxBackend
from insightclass.schemas import InferenceConfig


class OnnxBackendPostprocessTests(unittest.TestCase):
    def test_restores_letterboxed_boxes_to_source_coordinates(self):
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        _blob, scale, padding, original_shape = OnnxBackend._preprocess(frame, 200)

        # Model-space box: x=50..150, y=75..125. The image has 50px top
        # padding, so source-space y becomes 25..75.
        output = np.array(
            [[[100.0], [100.0], [100.0], [50.0], [0.9], [0.1]]],
            dtype=np.float32,
        )
        detections = OnnxBackend._postprocess(
            output, scale, padding, original_shape, 0.5, 0.45
        )

        self.assertEqual(len(detections), 1)
        np.testing.assert_allclose(
            detections[0]["xyxy"], [50.0, 25.0, 150.0, 75.0]
        )

    def test_nms_does_not_suppress_overlapping_different_classes(self):
        # Two identical boxes, each belonging to a different class.
        output = np.array(
            [[
                [50.0, 50.0],
                [50.0, 50.0],
                [40.0, 40.0],
                [40.0, 40.0],
                [0.9, 0.1],
                [0.1, 0.8],
            ]],
            dtype=np.float32,
        )
        detections = OnnxBackend._postprocess(
            output, 1.0, (0, 0), (100, 100), 0.5, 0.45
        )

        self.assertEqual({item["class_id"] for item in detections}, {0, 1})

    def test_video_inference_preserves_frame_indices_and_class_names(self):
        frames = [
            np.zeros((10, 20, 3), dtype=np.uint8),
            np.ones((10, 20, 3), dtype=np.uint8),
        ]

        class FakeCapture:
            def __init__(self, _source):
                self._frames = iter(frames)
                self.released = False

            def isOpened(self):
                return True

            def read(self):
                try:
                    return True, next(self._frames)
                except StopIteration:
                    return False, None

            def release(self):
                self.released = True

        config = InferenceConfig(
            backend="onnx",
            weights_path="model.onnx",
            source="video.mp4",
            output_dir="output",
            image_size=20,
            class_names=["phone_use"],
        )
        backend = OnnxBackend()
        detection = {"xyxy": [1, 2, 3, 4], "confidence": 0.9, "class_id": 0}
        with patch("insightclass.backends.onnx_backend.cv2.VideoCapture", FakeCapture):
            with patch.object(backend, "predict_frame", return_value=[detection]):
                predictions = backend.load_predictions_as_sv_detections(config)

        self.assertEqual([item.frame_index for item in predictions], [0, 1])
        self.assertEqual(predictions[0].detections[0].class_name, "phone_use")


if __name__ == "__main__":
    unittest.main()
