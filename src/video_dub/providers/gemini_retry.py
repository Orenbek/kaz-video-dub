from __future__ import annotations

from typing import Any


def build_gemini_http_options(types_module: Any, request_timeout_seconds: float | None) -> Any:
    options: dict[str, Any] = {
        # "retry_options": types_module.HttpRetryOptions(attempts=1),
    }
    if request_timeout_seconds is not None:
        options["timeout"] = max(1, int(request_timeout_seconds * 1000))
    return types_module.HttpOptions(**options)


def is_retryable_gemini_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    if isinstance(code, int) and 400 <= code < 500 and code != 429:
        return False
    return True
