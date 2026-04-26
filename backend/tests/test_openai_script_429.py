from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from worker.modules.script_generator.openai_provider import (
    OpenAIRateLimitedError,
    OpenAIScriptProvider,
    _MAX_ATTEMPTS,
)


def _make_429_response(retry_after: str | None = None) -> MagicMock:
    """Build a minimal mock httpx.Response for a 429."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 429
    resp.request = MagicMock()
    headers: dict[str, str] = {}
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    resp.headers = headers
    return resp


def _make_200_response(text: str = "Generated script") -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.request = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "choices": [{"message": {"content": text}}],
        "usage": {"total_tokens": 50},
    }
    return resp


class TestOpenAIScriptProvider429:
    @patch("worker.modules.script_generator.openai_provider.time.sleep")
    def test_raises_rate_limited_error_after_all_retries(self, mock_sleep):
        """All attempts return 429 → OpenAIRateLimitedError is raised."""
        provider = OpenAIScriptProvider()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = _make_429_response()

            with pytest.raises(OpenAIRateLimitedError):
                provider.generate(topic="AI")

        assert mock_client.post.call_count == _MAX_ATTEMPTS

    @patch("worker.modules.script_generator.openai_provider.time.sleep")
    def test_retries_before_raising(self, mock_sleep):
        """429 on first two attempts, success on third → returns ScriptResult."""
        provider = OpenAIScriptProvider()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.post.side_effect = [
                _make_429_response(),
                _make_429_response(),
                _make_200_response("Hello from OpenAI"),
            ]

            result = provider.generate(topic="AI")

        assert result.text == "Hello from OpenAI"
        assert mock_client.post.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("worker.modules.script_generator.openai_provider.time.sleep")
    def test_respects_retry_after_header(self, mock_sleep):
        """When Retry-After header is present its value is used as the wait time."""
        provider = OpenAIScriptProvider()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.post.side_effect = [
                _make_429_response(retry_after="5"),
                _make_429_response(retry_after="10"),
                _make_429_response(),
            ]

            with pytest.raises(OpenAIRateLimitedError):
                provider.generate(topic="AI")

        # First sleep should use Retry-After=5, second Retry-After=10
        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_calls[0] == 5.0
        assert sleep_calls[1] == 10.0

    @patch("worker.modules.script_generator.openai_provider.time.sleep")
    def test_uses_exponential_backoff_without_retry_after(self, mock_sleep):
        """Without Retry-After header, exponential backoff is used."""
        provider = OpenAIScriptProvider()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.post.side_effect = [
                _make_429_response(),
                _make_429_response(),
                _make_429_response(),
            ]

            with pytest.raises(OpenAIRateLimitedError):
                provider.generate(topic="AI")

        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
        # Attempt 1: 2^0 * BASE, Attempt 2: 2^1 * BASE
        assert sleep_calls[0] == 2.0
        assert sleep_calls[1] == 4.0
