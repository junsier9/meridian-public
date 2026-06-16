from __future__ import annotations

import os

from enhengclaw.providers.errors import ShadowProviderError


class MissingEnvironmentVariableError(ShadowProviderError):
    pass


def require_env(env_var: str) -> str:
    value = os.getenv(env_var)
    if value is None or not value.strip():
        raise MissingEnvironmentVariableError(
            f"missing required environment variable: {env_var}"
        )
    return value.strip()
