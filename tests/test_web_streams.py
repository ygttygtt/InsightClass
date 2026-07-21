import asyncio
import unittest
from unittest.mock import patch

from insightclass.web import server


class FakeStreamManager:
    def __init__(self):
        self.url = ""
        self.stopped = False

    def start(self, url):
        self.url = url
        return True

    def stop(self):
        self.stopped = True

    def get_status(self):
        return {"active": True, "status": "streaming", "error": ""}


class RtspStreamRegistryTests(unittest.TestCase):
    def test_registry_keeps_cameras_isolated(self):
        registry = server.RtspStreamRegistry(FakeStreamManager)

        first = registry.start("192.168.1.10", "rtsp://first")
        second = registry.start("192.168.1.11", "rtsp://second")

        self.assertIsNot(first, second)
        self.assertEqual(registry.get("192.168.1.10").url, "rtsp://first")
        self.assertEqual(registry.get("192.168.1.11").url, "rtsp://second")

    def test_status_contract_includes_active_and_camera_ip(self):
        registry = server.RtspStreamRegistry(FakeStreamManager)
        registry.start("192.168.1.10", "rtsp://first")

        status = registry.get_status("192.168.1.10")

        self.assertTrue(status["active"])
        self.assertEqual(status["status"], "streaming")
        self.assertEqual(status["camera_ip"], "192.168.1.10")


class CameraConfigurationTests(unittest.TestCase):
    def test_rtsp_url_encodes_credentials(self):
        url = server._build_rtsp_url(
            "192.168.1.10", username="user@example", password="p@ss:/word", port=554
        )

        self.assertEqual(
            url,
            "rtsp://user%40example:p%40ss%3A%2Fword@192.168.1.10:554/Streaming/Channels/101",
        )

    def test_invalid_camera_ip_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid camera IP"):
            server._validate_camera_ip("999.1.1.1")

    def test_camera_api_does_not_expose_rtsp_credentials(self):
        cameras = [{"ip": "192.168.1.10", "name": "Front"}]
        with patch.object(server, "_load_custom_cameras", return_value=cameras):
            result = server._build_camera_list()

        self.assertNotIn("rtsp_url", result[0])
        self.assertNotIn("password", result[0])

    def test_stream_status_api_matches_frontend_contract(self):
        fake_registry = server.RtspStreamRegistry(FakeStreamManager)
        fake_registry.start("192.168.1.10", "rtsp://first")
        with patch.object(server, "_stream_registry", fake_registry):
            response = asyncio.run(server.stream_status("192.168.1.10"))

        self.assertEqual(response.status_code, 200)
        payload = bytes(response.body)
        self.assertIn(b'"active":true', payload)
        self.assertIn(b'"camera_ip":"192.168.1.10"', payload)


if __name__ == "__main__":
    unittest.main()
