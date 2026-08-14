from __future__ import annotations

import contextlib
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import apsw

from .config import Settings


class LineDatabaseError(RuntimeError):
    """A structured, safe-to-display error while opening the local LINE database."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "DATABASE_UNAVAILABLE",
        retryable: bool = False,
        suggested_action: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.suggested_action = suggested_action


@contextlib.contextmanager
def open_encrypted_snapshot(snapshot: Path, key: str) -> Iterator[apsw.Connection]:
    connection = apsw.Connection(str(snapshot), flags=apsw.SQLITE_OPEN_READONLY)
    try:
        connection.pragma("cipher", "aes128cbc")
        with contextlib.suppress(Exception):
            connection.pragma("kdf_iter", 1)
        connection.pragma("key", key)
        yield connection
    finally:
        connection.close()


def discover_line_databases(home: Path | None = None) -> list[Path]:
    root = home or Path.home()
    patterns = (
        "Library/Containers/jp.naver.line.mac/Data/Library/Containers/jp.naver.line/Data/db/*.edb",
        "Library/Containers/jp.naver.line/Data/db/*.edb",
    )
    ranked: list[tuple[int, float, Path]] = []
    seen: set[Path] = set()
    for priority, pattern in enumerate(patterns):
        for path in root.glob(pattern):
            if path.is_file():
                with contextlib.suppress(OSError):
                    resolved = path.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        ranked.append((priority, -path.stat().st_mtime, resolved))
    ranked.sort()
    return [path for _, _, path in ranked]


def key_from_macos_keychain(service: str) -> str:
    try:
        value = subprocess.check_output(
            ["security", "find-generic-password", "-s", service, "-w"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=10,
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise LineDatabaseError(
            f"LINE database key is unavailable in macOS Keychain service '{service}'.",
            code="KEY_MISSING",
            suggested_action="Run line-local-mcp --setup-key, then retry the request.",
        ) from exc
    if not value:
        raise LineDatabaseError(
            "LINE database key in macOS Keychain is empty.",
            code="KEY_MISSING",
            suggested_action="Run line-local-mcp --setup-key, then retry the request.",
        )
    return value


class LineDatabase:
    """Creates disposable, read-only snapshots of LINE's encrypted SQLite database."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()

    def resolve_path(self) -> Path:
        if self.settings.db_path is not None:
            path = self.settings.db_path.resolve()
            if not path.is_file():
                raise LineDatabaseError(
                    "Configured LINE database file does not exist.",
                    code="DATABASE_NOT_FOUND",
                    suggested_action="Check LINE_MCP_DB_PATH or remove it to use automatic discovery.",
                )
            return path
        candidates = discover_line_databases()
        if not candidates:
            raise LineDatabaseError(
                "No LINE Desktop database was found. Install and sign in to LINE Desktop on this Mac.",
                code="DATABASE_NOT_FOUND",
                suggested_action="Open LINE Desktop, sign in, wait for synchronization, then retry.",
            )
        return candidates[0]

    @contextlib.contextmanager
    def connection(self) -> Iterator[apsw.Connection]:
        source = self.resolve_path()
        try:
            with tempfile.TemporaryDirectory(prefix="line-local-mcp-") as temp_dir:
                snapshot = Path(temp_dir) / source.name
                for suffix in ("", "-wal", "-shm"):
                    candidate = Path(f"{source}{suffix}")
                    if candidate.exists():
                        shutil.copy2(candidate, Path(f"{snapshot}{suffix}"))

                with open_encrypted_snapshot(
                    snapshot, key_from_macos_keychain(self.settings.keychain_service)
                ) as connection:
                    connection.setrowtrace(
                        lambda cursor, row: {
                            column[0]: row[index]
                            for index, column in enumerate(cursor.getdescription())
                        }
                    )
                    next(connection.cursor().execute("SELECT 1 FROM _message LIMIT 1"), None)
                    yield connection
        except LineDatabaseError:
            raise
        except (OSError, apsw.Error) as exc:
            raise LineDatabaseError(
                "LINE Desktop database could not be opened read-only. Check Full Disk Access and the stored key.",
                code="DATABASE_UNREADABLE",
                retryable=True,
                suggested_action=(
                    "Grant Full Disk Access to the MCP launcher; if access is already granted, "
                    "run line-local-mcp --setup-key and retry."
                ),
            ) from exc

    def modified_at(self) -> float:
        source = self.resolve_path()
        mtimes = []
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(f"{source}{suffix}")
            if candidate.exists():
                with contextlib.suppress(OSError):
                    mtimes.append(candidate.stat().st_mtime)
        if not mtimes:
            raise LineDatabaseError(
                "LINE database disappeared while checking its freshness.",
                code="DATABASE_NOT_FOUND",
                retryable=True,
                suggested_action="Open LINE Desktop, wait for synchronization, then retry.",
            )
        return max(mtimes)


ConnectionProvider = Any
