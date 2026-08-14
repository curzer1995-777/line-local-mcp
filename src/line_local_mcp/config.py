from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _env_nonnegative_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return max(0.0, parsed)


@dataclass(frozen=True)
class Settings:
    db_path: Path | None = None
    keychain_service: str = "line-cua-mcp-dbkey"
    redact_sensitive: bool = True
    snapshot_cache_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> Settings:
        configured_path = os.environ.get("LINE_MCP_DB_PATH")
        return cls(
            db_path=Path(configured_path).expanduser() if configured_path else None,
            keychain_service=os.environ.get(
                "LINE_MCP_KEYCHAIN_SERVICE", "line-cua-mcp-dbkey"
            ),
            redact_sensitive=_env_bool("LINE_MCP_REDACT_SENSITIVE", True),
            snapshot_cache_seconds=_env_nonnegative_float(
                "LINE_MCP_SNAPSHOT_CACHE_SECONDS", 30.0
            ),
        )
