from __future__ import annotations

from video_dub.providers.gemini_retry import is_retryable_gemini_error


class FakeGeminiError(Exception):
    def __init__(self, code: int) -> None:
        self.code = code
        super().__init__(str(code))


def test_non_rate_limit_client_errors_are_not_retryable() -> None:
    assert not is_retryable_gemini_error(FakeGeminiError(400))
    assert not is_retryable_gemini_error(FakeGeminiError(403))


def test_rate_limit_and_server_errors_are_retryable() -> None:
    assert is_retryable_gemini_error(FakeGeminiError(429))
    assert is_retryable_gemini_error(FakeGeminiError(500))
    assert is_retryable_gemini_error(RuntimeError("network timeout"))
