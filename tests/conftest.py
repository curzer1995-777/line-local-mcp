from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

import apsw
import pytest

from line_local_mcp.repository import LineRepository


class FixtureDatabase:
    def __init__(self, path: Path):
        self.path = path

    @contextlib.contextmanager
    def connection(self) -> Iterator[apsw.Connection]:
        connection = apsw.Connection(str(self.path), flags=apsw.SQLITE_OPEN_READONLY)
        connection.setrowtrace(
            lambda cursor, row: {
                column[0]: row[index]
                for index, column in enumerate(cursor.getdescription())
            }
        )
        try:
            yield connection
        finally:
            connection.close()

    def modified_at(self) -> float:
        return self.path.stat().st_mtime


@pytest.fixture
def repository(tmp_path: Path) -> LineRepository:
    path = tmp_path / "line-fixture.db"
    db = apsw.Connection(str(path))
    cursor = db.cursor()
    cursor.execute("CREATE TABLE _profile (_mid TEXT)")
    cursor.execute("INSERT INTO _profile VALUES ('me')")
    cursor.execute("CREATE TABLE _contact (_mid TEXT, _displayName TEXT, _capableBuddy INTEGER)")
    cursor.executemany(
        "INSERT INTO _contact VALUES (?, ?, ?)",
        [("alice", "Alice", 0), ("official", "Shop News", 1), ("me", "Me", 0)],
    )
    cursor.execute("CREATE TABLE _groupChat (_chatMid TEXT, _chatName TEXT)")
    cursor.execute("INSERT INTO _groupChat VALUES ('group-1', 'Project Team')")
    cursor.execute("CREATE TABLE _room (_mid TEXT)")
    cursor.execute(
        "CREATE TABLE _chat (_id TEXT, _midType INTEGER, _lastUpdatedTime INTEGER, _unreadCount INTEGER)"
    )
    cursor.executemany(
        "INSERT INTO _chat VALUES (?, ?, ?, ?)",
        [
            ("alice", 0, 1_786_500_000_000, 1),
            ("group-1", 2, 1_786_500_100_000, 0),
            ("official", 0, 1_786_500_200_000, 8),
        ],
    )
    cursor.execute(
        """
        CREATE TABLE _message (
          _id TEXT, _chatId TEXT, _from TEXT, _createdTime INTEGER,
          _text TEXT, _contentPreview TEXT, _contentMetadata TEXT, _contentType INTEGER
        )
        """
    )
    cursor.executemany(
        "INSERT INTO _message VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("m1", "alice", "alice", 1_786_500_000_000, "Can you confirm?", None, None, 0),
            ("m2", "alice", "me", 1_786_500_010_000, "Yes. password: abc123", None, None, 0),
            ("m3", "group-1", "alice", 1_786_500_100_000, "Project update", None, None, 0),
            ("m4", "official", "official", 1_786_500_200_000, "Project sale", None, None, 0),
        ],
    )
    db.close()
    return LineRepository(FixtureDatabase(path), redact_sensitive=True)
