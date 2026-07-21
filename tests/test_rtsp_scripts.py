import unittest

from scripts import record_multi_rtsp, rtsp_preview


class RtspScriptTests(unittest.TestCase):
    def test_recording_url_escapes_credentials(self):
        url = record_multi_rtsp.build_rtsp_url(
            "192.0.2.10", "user@example", "p@ss:/word", 8554, "102"
        )

        self.assertEqual(
            url,
            "rtsp://user%40example:p%40ss%3A%2Fword@192.0.2.10:8554/Streaming/Channels/102",
        )

    def test_preview_url_supports_anonymous_stream(self):
        url = rtsp_preview.build_rtsp_url("192.0.2.10", "", "", 554, "101")

        self.assertEqual(
            url, "rtsp://192.0.2.10:554/Streaming/Channels/101"
        )

    def test_password_comes_from_environment_without_a_default(self):
        self.assertEqual(
            record_multi_rtsp.resolve_password(None, {"INSIGHTCLASS_RTSP_PASSWORD": "secret"}),
            "secret",
        )
        self.assertEqual(rtsp_preview.resolve_password("explicit", {}), "explicit")

    def test_invalid_ip_and_channel_are_rejected(self):
        with self.assertRaises(ValueError):
            record_multi_rtsp.build_rtsp_url("not-an-ip", "admin", "secret")
        with self.assertRaisesRegex(ValueError, "channel"):
            rtsp_preview.build_rtsp_url(
                "192.0.2.10", "admin", "secret", channel="103"
            )


if __name__ == "__main__":
    unittest.main()
