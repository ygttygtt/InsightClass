import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from insightclass import __version__
from insightclass.web.llm import (
    LlmClientError,
    OpenAICompatibleClient,
    OpenAICompatibleConfig,
    normalize_base_url,
)
from insightclass.web import server


class FakeRequestBody:
    def __init__(self, body):
        self.body = body

    async def json(self):
        return self.body


class FakeResponse:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


class OpenAICompatibleClientTests(unittest.TestCase):
    def test_normalizes_full_chat_completions_url(self):
        self.assertEqual(
            normalize_base_url("https://example.com/v1/chat/completions/"),
            "https://example.com/v1",
        )

    def test_rejects_non_http_base_urls(self):
        with self.assertRaisesRegex(ValueError, "HTTP or HTTPS"):
            normalize_base_url("file:///tmp/model")

    def test_sends_chat_completions_request_and_parses_response(self):
        response = FakeResponse({
            "model": "demo-model",
            "choices": [{"message": {"content": " Analysis complete. "}}],
            "usage": {"total_tokens": 12},
        })
        config = OpenAICompatibleConfig(
            base_url="https://example.com/v1",
            model="demo-model",
            api_key="secret",
        )
        client = OpenAICompatibleClient(config)

        with patch("insightclass.web.llm.urllib.request.urlopen", return_value=response) as urlopen:
            result = client.chat([{"role": "user", "content": "Analyze"}])

        request = urlopen.call_args.args[0]
        sent = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://example.com/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(request.get_header("User-agent"), f"InsightClass/{__version__}")
        self.assertEqual(sent["model"], "demo-model")
        self.assertEqual(result["content"], "Analysis complete.")

    def test_rejects_invalid_provider_response(self):
        client = OpenAICompatibleClient(OpenAICompatibleConfig(
            base_url="http://127.0.0.1:11434/v1",
            model="local-model",
        ))
        with patch(
            "insightclass.web.llm.urllib.request.urlopen",
            return_value=FakeResponse({"unexpected": True}),
        ):
            with self.assertRaises(LlmClientError):
                client.chat([{"role": "user", "content": "Analyze"}])


class LlmApiTests(unittest.TestCase):
    def test_settings_save_key_without_returning_plaintext(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            app_config = Path(tmp_dir) / "app.yaml"
            with patch.object(server, "APP_CONFIG", app_config):
                with patch.dict(server.os.environ, {}, clear=True):
                    response = asyncio.run(server.set_llm_settings(FakeRequestBody({
                        "base_url": "http://127.0.0.1:11434/v1",
                        "model": "local-model",
                        "api_key": "top-secret",
                        "timeout": 30,
                    })))
                    stored = server._load_app_config()["llm"]

        self.assertEqual(stored["api_key"], "top-secret")
        self.assertNotIn(b"top-secret", bytes(response.body))
        self.assertIn(b'"has_api_key":true', bytes(response.body))

    def test_analysis_sends_json_context_to_client(self):
        class Client:
            def __init__(self):
                self.messages = []

            def chat(self, messages, **_kwargs):
                self.messages = messages
                return {"content": "建议内容", "model": "local-model", "usage": {}}

        client = Client()
        request = FakeRequestBody({
            "prompt": "分析风险",
            "context": {"total": {"phone_use": 2}},
        })
        with patch.object(server, "_build_llm_client", return_value=client):
            response = asyncio.run(server.analyze_with_llm(request))

        self.assertIn("phone_use", client.messages[1]["content"])
        self.assertIn("建议内容", bytes(response.body).decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
