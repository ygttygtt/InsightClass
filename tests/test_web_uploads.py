import asyncio
import io
import unittest
from unittest.mock import patch

from fastapi import HTTPException, UploadFile

from insightclass.web import server


def upload(filename: str, contents: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(contents), size=len(contents))


class UploadValidationTests(unittest.TestCase):
    def test_frame_upload_rejects_oversized_content(self):
        with patch.object(server, "MAX_IMAGE_UPLOAD_BYTES", 4):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(server.detect_frame(upload("frame.jpg", b"12345"), "", 0.5, 0.45))

        self.assertEqual(raised.exception.status_code, 413)

    def test_frame_upload_rejects_unsupported_extension(self):
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(server.detect_frame(upload("frame.txt", b"data"), "", 0.5, 0.45))

        self.assertEqual(raised.exception.status_code, 415)

    def test_batch_upload_rejects_too_many_files_before_writing(self):
        videos = [upload("one.mp4", b"1"), upload("two.mp4", b"2")]
        with patch.object(server, "MAX_BATCH_FILES", 1):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(server.batch_upload(videos))

        self.assertEqual(raised.exception.status_code, 413)


class BatchLifecycleTests(unittest.TestCase):
    def test_batch_cannot_be_started_twice(self):
        job = {
            "batch_id": "batch1",
            "status": "pending",
            "items": [],
            "total_latency_sec": 0,
            "_dir": "",
        }
        with patch.dict(server._batch_jobs, {"batch1": job}, clear=True), patch.object(
            server, "_resolve_weights_path", return_value="model.onnx"
        ), patch.object(server.threading, "Thread") as thread:
            first = asyncio.run(server.batch_detect("batch1", "", 0.5, 0.45))
            second = asyncio.run(server.batch_detect("batch1", "", 0.5, 0.45))

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        thread.assert_called_once()


if __name__ == "__main__":
    unittest.main()
