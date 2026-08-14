from __future__ import annotations

import contextlib
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import apsw

from line_local_mcp.config import Settings
from line_local_mcp.database import LineDatabase
from line_local_mcp.repository import LineRepository


@contextlib.contextmanager
def open_plain_snapshot(snapshot: Path, key: str):
    del key
    connection = apsw.Connection(str(snapshot), flags=apsw.SQLITE_OPEN_READONLY)
    try:
        yield connection
    finally:
        connection.close()


def create_source(path: Path, message_count: int = 1) -> None:
    connection = apsw.Connection(str(path))
    cursor = connection.cursor()
    cursor.execute("CREATE TABLE _message (_id TEXT, _createdTime INTEGER)")
    cursor.executemany(
        "INSERT INTO _message VALUES (?, ?)",
        [(f"m{index}", index) for index in range(message_count)],
    )
    connection.close()


def append_message(path: Path, message_id: str) -> None:
    connection = apsw.Connection(str(path))
    connection.cursor().execute(
        "INSERT INTO _message VALUES (?, ?)", (message_id, 9_999)
    )
    connection.close()


class CopySpy:
    def __init__(self, *, mutate_after_first_copy=None):
        self.calls = 0
        self.mutate_after_first_copy = mutate_after_first_copy

    def __call__(self, source: Path, destination: Path) -> None:
        self.calls += 1
        shutil.copy2(source, destination)
        if self.calls == 1 and self.mutate_after_first_copy is not None:
            self.mutate_after_first_copy()


def create_database(
    path: Path, copy_spy: CopySpy, key_calls: list[str]
) -> LineDatabase:
    return LineDatabase(
        Settings(db_path=path, snapshot_cache_seconds=60),
        key_loader=lambda service: key_calls.append(service) or "test-key",
        copy_file=copy_spy,
        snapshot_opener=open_plain_snapshot,
    )


def message_count(connection) -> int:
    return (
        connection.cursor()
        .execute("SELECT COUNT(*) AS n FROM _message")
        .fetchone()["n"]
    )


def test_reuses_snapshot_and_key_for_unchanged_source(tmp_path):
    source = tmp_path / "line.db"
    create_source(source)
    copies = CopySpy()
    key_calls: list[str] = []
    database = create_database(source, copies, key_calls)

    with database.connection() as first:
        first_id = first.snapshot_id
        assert message_count(first) == 1
    with database.connection() as second:
        assert second.snapshot_id == first_id
        assert second.cache_hit is True
        assert message_count(second) == 1

    assert copies.calls == 1
    assert key_calls == ["line-cua-mcp-dbkey"]
    assert database.cache_info() == {
        "enabled": True,
        "ttl_seconds": 60,
        "hits": 1,
        "misses": 1,
        "rebuilds": 1,
        "consistency_retries": 0,
        "keychain_reads": 1,
    }


def test_source_change_creates_new_generation_without_stale_results(tmp_path):
    source = tmp_path / "line.db"
    create_source(source)
    copies = CopySpy()
    database = create_database(source, copies, [])

    with database.connection() as first:
        first_id = first.snapshot_id
        assert message_count(first) == 1

    append_message(source, "m-new")

    with database.connection() as second:
        assert second.snapshot_id != first_id
        assert second.cache_hit is False
        assert message_count(second) == 2

    assert copies.calls == 2


def test_copy_retries_if_source_changes_mid_snapshot(tmp_path):
    source = tmp_path / "line.db"
    create_source(source)
    copies = CopySpy(mutate_after_first_copy=lambda: append_message(source, "m-new"))
    database = create_database(source, copies, [])

    with database.connection() as connection:
        assert message_count(connection) == 2

    assert copies.calls == 2
    assert database.cache_info()["consistency_retries"] == 1


def test_active_reader_keeps_consistent_retired_snapshot(tmp_path):
    source = tmp_path / "line.db"
    create_source(source)
    database = create_database(source, CopySpy(), [])

    with database.connection() as first:
        first_snapshot = first.snapshot_path
        first_id = first.snapshot_id
        append_message(source, "m-new")

        with database.connection() as second:
            assert second.snapshot_id != first_id
            assert message_count(second) == 2
            assert first_snapshot.exists()

        assert message_count(first) == 1
        assert first_snapshot.exists()

    assert not first_snapshot.exists()


def test_snapshot_ttl_rebuilds_without_rereading_keychain(tmp_path):
    source = tmp_path / "line.db"
    create_source(source)
    copies = CopySpy()
    key_calls: list[str] = []
    now = [0.0]
    database = LineDatabase(
        Settings(db_path=source, snapshot_cache_seconds=5),
        key_loader=lambda service: key_calls.append(service) or "test-key",
        copy_file=copies,
        snapshot_opener=open_plain_snapshot,
        clock=lambda: now[0],
    )

    with database.connection() as first:
        first_path = first.snapshot_path
    now[0] = 6.0
    with database.connection() as second:
        assert second.snapshot_path != first_path
        assert message_count(second) == 1

    assert copies.calls == 2
    assert len(key_calls) == 1
    assert database.cache_info()["misses"] == 2


def _without_snapshot_id(result: dict) -> dict:
    comparable = dict(result)
    comparable.pop("snapshot_id", None)
    return comparable


def test_cached_repository_preserves_full_result_and_reuses_name_maps(repository):
    source = repository.database.path
    database = create_database(source, CopySpy(), [])
    cached_repository = LineRepository(database, redact_sensitive=True)
    arguments = {
        "after": "2020-01-01T00:00:00+00:00",
        "before": "2030-01-01T00:00:00+00:00",
    }
    reference = repository.read_chat_activity("project", **arguments)

    with (
        mock.patch.object(
            cached_repository,
            "_load_name_maps",
            wraps=cached_repository._load_name_maps,
        ) as load_name_maps,
        mock.patch.object(
            cached_repository,
            "_load_chat_directory",
            wraps=cached_repository._load_chat_directory,
        ) as load_chat_directory,
        mock.patch.object(
            cached_repository,
            "_load_source_newest_message_at",
            wraps=cached_repository._load_source_newest_message_at,
        ) as load_source_newest,
    ):
        cold = cached_repository.read_chat_activity("project", **arguments)
        warm = cached_repository.read_chat_activity("project", **arguments)

    assert _without_snapshot_id(cold) == _without_snapshot_id(reference)
    assert warm == cold
    assert cold["snapshot_id"]
    assert load_name_maps.call_count == 1
    assert load_chat_directory.call_count == 1
    assert load_source_newest.call_count == 1


def test_parallel_readers_share_generation_and_return_identical_data(repository):
    source = repository.database.path
    copies = CopySpy()
    key_calls: list[str] = []
    database = create_database(source, copies, key_calls)
    cached_repository = LineRepository(database, redact_sensitive=True)
    arguments = {
        "after": "2020-01-01T00:00:00+00:00",
        "before": "2030-01-01T00:00:00+00:00",
    }

    def read_activity(_: int) -> dict:
        return cached_repository.read_chat_activity("project", **arguments)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(read_activity, range(8)))

    assert all(result == results[0] for result in results)
    assert len({result["snapshot_id"] for result in results}) == 1
    assert copies.calls == 1
    assert len(key_calls) == 1
    assert database.cache_info()["hits"] == 7
