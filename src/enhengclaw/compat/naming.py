from __future__ import annotations

from collections.abc import MutableMapping
from typing import Mapping


PROJECT_DISPLAY_NAME = "Meridian Alpha Platform"
PROJECT_SLUG = "meridian_alpha"
PROJECT_ENV_PREFIX = "MERIDIAN_ALPHA_"

LEGACY_PROJECT_DISPLAY_NAME = "EnhengClaw"
LEGACY_PROJECT_SLUG = "enhengclaw"
LEGACY_ENV_PREFIX = "ENHENGCLAW_"


def primary_env_name(name: str) -> str:
    env_name = str(name)
    if env_name.startswith(LEGACY_ENV_PREFIX):
        return f"{PROJECT_ENV_PREFIX}{env_name.removeprefix(LEGACY_ENV_PREFIX)}"
    return env_name


def legacy_env_name(name: str) -> str:
    env_name = str(name)
    if env_name.startswith(PROJECT_ENV_PREFIX):
        return f"{LEGACY_ENV_PREFIX}{env_name.removeprefix(PROJECT_ENV_PREFIX)}"
    return env_name


def env_aliases(name: str) -> tuple[str, ...]:
    env_name = str(name)
    primary = primary_env_name(env_name)
    legacy = legacy_env_name(env_name)
    if primary == legacy:
        return (env_name,)
    return (primary, legacy)


def env_aliases_text(name: str) -> str:
    aliases = env_aliases(name)
    if len(aliases) == 1:
        return aliases[0]
    return f"{aliases[0]} (legacy {aliases[1]})"


def getenv_compat(
    name: str,
    default: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> str | None:
    source = env if env is not None else __import__("os").environ
    for candidate in env_aliases(name):
        if candidate in source:
            return source[candidate]
    return default


def materialize_env_alias(
    env: MutableMapping[str, str],
    name: str,
    value: str | None = None,
    *,
    default: str | None = None,
) -> str | None:
    resolved = value if value is not None else getenv_compat(name, default, env=env)
    if resolved is None:
        return None
    for candidate in env_aliases(name):
        env[candidate] = resolved
    return resolved


def pop_env_aliases(env: MutableMapping[str, str], name: str) -> None:
    for candidate in env_aliases(name):
        env.pop(candidate, None)
