"""Minimal client for OpenAI-compatible Chat Completions providers."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit


class LlmClientError(RuntimeError):
    """A provider, transport or response-format error safe to show in the UI."""


@dataclass(frozen=True, slots=True)
class OpenAICompatibleConfig:
    base_url: str
    model: str
    api_key: str = ""
    timeout: float = 60.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", normalize_base_url(self.base_url))
        if not self.model.strip():
            raise ValueError("Model is required")
        object.__setattr__(self, "model", self.model.strip())
        if not 1 <= float(self.timeout) <= 300:
            raise ValueError("Timeout must be between 1 and 300 seconds")


def normalize_base_url(value: str) -> str:
    raw = value.strip().rstrip("/")
    if not raw:
        raise ValueError("Base URL is required")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Base URL must be an HTTP or HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("Base URL must not contain credentials")
    path = parsed.path.rstrip("/")
    if path.endswith("/chat/completions"):
        path = path[: -len("/chat/completions")]
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


class OpenAICompatibleClient:
    def __init__(self, config: OpenAICompatibleConfig):
        self.config = config

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        if not messages:
            raise ValueError("At least one message is required")
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "InsightClass/0.1",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        request = urllib.request.Request(
            f"{self.config.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            message = _provider_error_message(exc.read())
            raise LlmClientError(
                f"Provider returned HTTP {exc.code}: {message}"
            ) from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise LlmClientError(f"Unable to reach model provider: {reason}") from exc
        except TimeoutError as exc:
            raise LlmClientError("Model provider request timed out") from exc

        try:
            data = json.loads(body.decode("utf-8"))
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise LlmClientError("Provider returned an invalid Chat Completions response") from exc

        if isinstance(content, list):
            content = "".join(
                str(part.get("text", ""))
                for part in content
                if isinstance(part, dict)
            )
        if not isinstance(content, str) or not content.strip():
            raise LlmClientError("Provider returned an empty response")
        return {
            "content": content.strip(),
            "model": str(data.get("model", self.config.model)),
            "usage": data.get("usage", {}),
        }


def _provider_error_message(body: bytes) -> str:
    try:
        payload = json.loads(body[:4096].decode("utf-8", errors="replace"))
        error = payload.get("error", {})
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
    except (json.JSONDecodeError, AttributeError):
        pass
    return "request failed"
