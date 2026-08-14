from __future__ import annotations

import contextlib
import hashlib
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
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
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as exc:
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


@dataclass(frozen=True)
class SourceFileFingerprint:
    suffix: str
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int


@dataclass(frozen=True)
class SourceFingerprint:
    source: str
    files: tuple[SourceFileFingerprint, ...]

    @property
    def snapshot_id(self) -> str:
        digest = hashlib.sha256(repr(self).encode()).hexdigest()
        return digest[:16]


@dataclass
class CachedSnapshot:
    fingerprint: SourceFingerprint
    snapshot_id: str
    temp_dir: tempfile.TemporaryDirectory[str]
    path: Path
    created_at: float
    leases: int = 0
    retired: bool = False


class SnapshotConnection:
    """APSW connection plus immutable snapshot provenance for repository caches."""

    def __init__(
        self,
        connection: apsw.Connection,
        *,
        snapshot_id: str,
        snapshot_path: Path,
        cache_hit: bool,
        cache_token: SourceFingerprint,
    ):
        self._connection = connection
        self.snapshot_id = snapshot_id
        self.snapshot_path = snapshot_path
        self.cache_hit = cache_hit
        self.cache_token = cache_token

    def cursor(self):
        return self._connection.cursor()

    def __getattr__(self, name: str):
        return getattr(self._connection, name)


class LineDatabase:
    """Creates generation-aware, read-only snapshots of LINE's encrypted database."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        key_loader: Callable[[str], str] | None = None,
        copy_file: Callable[[Path, Path], Any] | None = None,
        snapshot_opener: Callable[[Path, str], Any] | None = None,
        clock: Callable[[], float] | None = None,
        snapshot_attempts: int = 3,
    ):
        self.settings = settings or Settings.from_env()
        self._key_loader = key_loader or key_from_macos_keychain
        self._copy_file = copy_file or shutil.copy2
        self._snapshot_opener = snapshot_opener or open_encrypted_snapshot
        self._clock = clock or time.monotonic
        self._snapshot_attempts = max(1, snapshot_attempts)
        self._cache_lock = threading.RLock()
        self._snapshot: CachedSnapshot | None = None
        self._cached_key: str | None = None
        self._hits = 0
        self._misses = 0
        self._rebuilds = 0
        self._consistency_retries = 0
        self._keychain_reads = 0

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

    @staticmethod
    def _source_fingerprint(source: Path) -> SourceFingerprint:
        files: list[SourceFileFingerprint] = []
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(f"{source}{suffix}")
            try:
                stat = candidate.stat()
            except FileNotFoundError:
                if not suffix:
                    raise LineDatabaseError(
                        "LINE Desktop database disappeared while preparing a snapshot.",
                        code="DATABASE_NOT_FOUND",
                        retryable=True,
                        suggested_action="Open LINE Desktop, wait for synchronization, then retry.",
                    )
                continue
            files.append(
                SourceFileFingerprint(
                    suffix=suffix,
                    device=stat.st_dev,
                    inode=stat.st_ino,
                    size=stat.st_size,
                    modified_ns=stat.st_mtime_ns,
                    changed_ns=stat.st_ctime_ns,
                )
            )
        return SourceFingerprint(source=str(source), files=tuple(files))

    def _key(self) -> str:
        with self._cache_lock:
            if self._cached_key is None:
                self._keychain_reads += 1
                self._cached_key = self._key_loader(self.settings.keychain_service)
            return self._cached_key

    def _build_snapshot(self, source: Path) -> CachedSnapshot:
        for attempt in range(self._snapshot_attempts):
            before = self._source_fingerprint(source)
            temp_dir = tempfile.TemporaryDirectory(prefix="line-local-mcp-")
            snapshot = Path(temp_dir.name) / source.name
            try:
                for file in before.files:
                    self._copy_file(
                        Path(f"{source}{file.suffix}"),
                        Path(f"{snapshot}{file.suffix}"),
                    )
                after = self._source_fingerprint(source)
            except PermissionError:
                temp_dir.cleanup()
                raise
            except OSError:
                temp_dir.cleanup()
                if attempt + 1 < self._snapshot_attempts:
                    self._consistency_retries += 1
                    continue
                raise
            if before == after:
                self._rebuilds += 1
                return CachedSnapshot(
                    fingerprint=before,
                    snapshot_id=before.snapshot_id,
                    temp_dir=temp_dir,
                    path=snapshot,
                    created_at=self._clock(),
                )
            temp_dir.cleanup()
            self._consistency_retries += 1

        raise LineDatabaseError(
            "LINE Desktop changed continuously while creating a consistent snapshot.",
            code="DATABASE_CHANGING",
            retryable=True,
            suggested_action="Wait for LINE Desktop synchronization to settle, then retry.",
        )

    @staticmethod
    def _cleanup_snapshot(snapshot: CachedSnapshot) -> None:
        snapshot.temp_dir.cleanup()

    def _retire_snapshot(self, snapshot: CachedSnapshot) -> None:
        snapshot.retired = True
        if snapshot.leases == 0:
            self._cleanup_snapshot(snapshot)

    @contextlib.contextmanager
    def _snapshot_lease(self, source: Path) -> Iterator[tuple[CachedSnapshot, bool]]:
        fingerprint = self._source_fingerprint(source)
        with self._cache_lock:
            now = self._clock()
            current = self._snapshot
            cache_hit = bool(
                current
                and self.settings.snapshot_cache_seconds > 0
                and current.fingerprint == fingerprint
                and now - current.created_at <= self.settings.snapshot_cache_seconds
            )
            if cache_hit:
                snapshot = current
                self._hits += 1
            else:
                self._misses += 1
                snapshot = self._build_snapshot(source)
                old_snapshot = self._snapshot
                self._snapshot = snapshot
                if old_snapshot is not None:
                    self._retire_snapshot(old_snapshot)
            snapshot.leases += 1
        try:
            yield snapshot, cache_hit
        finally:
            with self._cache_lock:
                snapshot.leases -= 1
                if snapshot.retired and snapshot.leases == 0:
                    self._cleanup_snapshot(snapshot)

    def _invalidate_snapshot(self, snapshot: CachedSnapshot) -> None:
        with self._cache_lock:
            if self._snapshot is snapshot:
                self._snapshot = None
            self._retire_snapshot(snapshot)

    def cache_info(self) -> dict[str, Any]:
        with self._cache_lock:
            return {
                "enabled": self.settings.snapshot_cache_seconds > 0,
                "ttl_seconds": self.settings.snapshot_cache_seconds,
                "hits": self._hits,
                "misses": self._misses,
                "rebuilds": self._rebuilds,
                "consistency_retries": self._consistency_retries,
                "keychain_reads": self._keychain_reads,
            }

    @contextlib.contextmanager
    def connection(self) -> Iterator[SnapshotConnection]:
        source = self.resolve_path()
        try:
            with self._snapshot_lease(source) as (snapshot, cache_hit):
                validated = False
                try:
                    opener = self._snapshot_opener(snapshot.path, self._key())
                    with opener as connection:
                        connection.setrowtrace(
                            lambda cursor, row: {
                                column[0]: row[index]
                                for index, column in enumerate(cursor.getdescription())
                            }
                        )
                        next(
                            connection.cursor().execute(
                                "SELECT 1 FROM _message LIMIT 1"
                            ),
                            None,
                        )
                        validated = True
                        yield SnapshotConnection(
                            connection,
                            snapshot_id=snapshot.snapshot_id,
                            snapshot_path=snapshot.path,
                            cache_hit=cache_hit,
                            cache_token=snapshot.fingerprint,
                        )
                except apsw.Error:
                    if not validated:
                        self._invalidate_snapshot(snapshot)
                        with self._cache_lock:
                            self._cached_key = None
                    raise
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
        fingerprint = self._source_fingerprint(source)
        return max(file.modified_ns for file in fingerprint.files) / 1_000_000_000


ConnectionProvider = Any
