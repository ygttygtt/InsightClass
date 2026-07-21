import asyncio
import io
import unittest
from unittest.mock import patch

from fastapi import HTTPException, UploadFile

from insightclass.web import server


class JsonRequest:
    def __init__(self, payload):
        self.payload = payload

    async def json(self):
        return self.payload


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
    def test_rtsp_credentials_have_no_bundled_default_password(self):
        with patch.object(server, "_load_app_config", return_value={}):
            credentials = server._get_rtsp_credentials()

        self.assertEqual(credentials["password"], "")

    def test_rtsp_credentials_response_masks_password(self):
        with patch.object(server, "_get_rtsp_credentials", return_value={
            "username": "admin", "password": "secret-value", "port": 554,
        }):
            response = asyncio.run(server.get_rtsp_credentials())

        self.assertNotIn(b"secret-value", bytes(response.body))
        self.assertIn(b'"has_password":true', bytes(response.body))
        self.assertIn(b'"password_masked":"...alue"', bytes(response.body))

    def test_rtsp_credentials_update_preserves_blank_password(self):
        with patch.object(server, "_get_rtsp_credentials", return_value={
            "username": "old-user", "password": "old-password", "port": 554,
        }), patch.object(server, "_update_app_config") as update, patch.object(
            server._stream_registry, "stop_all"
        ):
            response = asyncio.run(server.set_rtsp_credentials(JsonRequest({
                "username": "new-user", "password": "", "port": 8554,
            })))

        self.assertEqual(response.status_code, 200)
        update.assert_called_once_with({"rtsp_credentials": {
            "username": "new-user", "password": "old-password", "port": 8554,
        }})

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


class ModelLifecycleTests(unittest.TestCase):
    def test_startup_weights_prefer_valid_saved_model(self):
        with patch.object(server, "_get_default_model", return_value="saved.onnx"), patch.object(
            server, "_validate_weights_path", return_value="validated.onnx"
        ), patch.object(server, "_find_default_weights") as discover:
            result = server._find_startup_weights()

        self.assertEqual(result, "validated.onnx")
        discover.assert_not_called()

    def test_startup_weights_fall_back_when_saved_model_is_stale(self):
        with patch.object(server, "_get_default_model", return_value="missing.onnx"), patch.object(
            server, "_validate_weights_path", side_effect=FileNotFoundError("missing")
        ), patch.object(server, "_find_default_weights", return_value="bundled.onnx"):
            result = server._find_startup_weights()

        self.assertEqual(result, "bundled.onnx")

    def test_system_status_uses_frontend_model_contract(self):
        with patch.object(server, "_get_model_state", return_value={
            "status": "ready", "model": "model.onnx", "error": "",
        }):
            response = asyncio.run(server.system_status())

        payload = bytes(response.body)
        self.assertIn(b'"model":"model.onnx"', payload)
        self.assertNotIn(b'"weights_path"', payload)

    def test_preload_worker_reports_ready(self):
        class Backend:
            def _load_model(self, _path):
                return None

        with patch.object(server, "_get_onnx_backend", return_value=Backend()):
            server._preload_model_worker("model.onnx")

        self.assertEqual(server._get_model_state()["status"], "ready")

    def test_preload_worker_reports_errors(self):
        class Backend:
            def _load_model(self, _path):
                raise RuntimeError("broken model")

        with patch.object(server, "_get_onnx_backend", return_value=Backend()):
            server._preload_model_worker("model.onnx")

        state = server._get_model_state()
        self.assertEqual(state["status"], "error")
        self.assertIn("broken model", state["error"])

    def test_invalid_frame_is_a_client_error(self):
        upload = UploadFile(filename="frame.jpg", file=io.BytesIO(b"not-an-image"))

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(server.detect_frame(upload, "", 0.5, 0.45))

        self.assertEqual(raised.exception.status_code, 400)


class DashboardStatsTests(unittest.TestCase):
    def test_history_uses_real_hourly_counts(self):
        stats = server.DashboardStats()
        with patch("insightclass.web.server.time.time", return_value=1_750_000_000):
            stats.record("192.168.1.10", "phone_use")
            history = stats.get_history(["192.168.1.10"])

        self.assertEqual(len(history["192.168.1.10"]), 24)
        self.assertEqual(history["192.168.1.10"][-1]["phone_use"], 1)
        self.assertEqual(history["192.168.1.10"][-1]["talking"], 0)

    def test_dashboard_total_only_includes_configured_cameras(self):
        stats = server.DashboardStats()
        stats.record("192.168.1.10", "phone_use")
        stats.record("upload", "talking")
        cameras = [{
            "ip": "192.168.1.10",
            "name": "Front",
            "group": "front",
            "group_label": "Front",
            "_status": "unknown",
        }]
        with patch.object(server, "_dashboard_stats", stats):
            with patch.object(server, "_build_camera_list", return_value=cameras):
                response = asyncio.run(server.dashboard_stats())

        body = bytes(response.body)
        self.assertIn(b'"phone_use":1', body)
        self.assertIn(b'"talking":0', body)
        self.assertIn(b'"status":"unknown"', body)


if __name__ == "__main__":
    unittest.main()
