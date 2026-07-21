import unittest

import numpy as np

from insightclass.backends.onnx_backend import OnnxBackend


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


if __name__ == "__main__":
    unittest.main()
