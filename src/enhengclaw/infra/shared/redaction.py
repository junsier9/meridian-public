from __future__ import annotations


def redact_secret_url(url: str) -> str:
    marker = "/v2/"
    if marker in url:
        prefix, _, _ = url.partition(marker)
        return f"{prefix}{marker}***redacted***"
    return url.split("?", maxsplit=1)[0]
