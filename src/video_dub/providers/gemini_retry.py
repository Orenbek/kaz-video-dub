from __future__ import annotations


def is_retryable_gemini_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    if isinstance(code, int) and 400 <= code < 500 and code != 429:
        return False
    return True
