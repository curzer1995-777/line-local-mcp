from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from .config import Settings
from .database import ConnectionProvider, LineDatabase
from .redaction import redact_text


def _to_millis(value: str | None) -> int | None:
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return int(parsed.timestamp() * 1000)


def _iso_time(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000).astimezone().isoformat(timespec="seconds")


def _chat_type(mid_type: int | None) -> str:
    return {0: "direct", 1: "room", 2: "group"}.get(mid_type, "other")


def _message_text(row: dict[str, Any]) -> str:
    if row.get("_text"):
        return str(row["_text"])
    if row.get("_contentPreview"):
        return str(row["_contentPreview"])
    metadata = row.get("_contentMetadata")
    if metadata:
        try:
            parsed = json.loads(metadata)
            for key in ("ALT_TEXT", "altText", "text", "title"):
                if parsed.get(key):
                    return str(parsed[key])
        except (TypeError, ValueError):
            pass
    labels = {1: "[image]", 2: "[video]", 3: "[audio]", 7: "[sticker]", 14: "[file]"}
    return labels.get(row.get("_contentType"), "[non-text message]")


class LineRepository:
    def __init__(
        self,
        database: ConnectionProvider | None = None,
        *,
        redact_sensitive: bool | None = None,
    ):
        settings = Settings.from_env()
        self.database = database or LineDatabase(settings)
        self.redact_sensitive = settings.redact_sensitive if redact_sensitive is None else redact_sensitive

    @staticmethod
    def _profile_mid(cursor: Any) -> str | None:
        row = next(cursor.execute("SELECT _mid FROM _profile LIMIT 1"), None)
        return row["_mid"] if row else None

    @staticmethod
    def _name_maps(cursor: Any) -> tuple[dict[str, str], dict[str, str], dict[str, str], set[str]]:
        contacts: dict[str, str] = {}
        official: set[str] = set()
        for row in cursor.execute("SELECT _mid, _displayName, _capableBuddy FROM _contact"):
            contacts[row["_mid"]] = row["_displayName"] or row["_mid"]
            if row["_capableBuddy"] == 1:
                official.add(row["_mid"])
        groups = {
            row["_chatMid"]: row["_chatName"] or row["_chatMid"]
            for row in cursor.execute("SELECT _chatMid, _chatName FROM _groupChat")
        }
        rooms = {
            row["_mid"]: row["_mid"]
            for row in cursor.execute("SELECT _mid FROM _room")
        }
        return contacts, groups, rooms, official

    @staticmethod
    def _chat_name(
        chat_id: str,
        mid_type: int | None,
        contacts: dict[str, str],
        groups: dict[str, str],
        rooms: dict[str, str],
    ) -> str:
        if mid_type == 0:
            return contacts.get(chat_id, chat_id)
        if mid_type == 2:
            return groups.get(chat_id, chat_id)
        if mid_type == 1:
            return rooms.get(chat_id, chat_id)
        return chat_id

    def _safe_text(self, value: str) -> tuple[str, bool]:
        if not self.redact_sensitive:
            return value, False
        return redact_text(value)

    def status(self) -> dict[str, Any]:
        with self.database.connection() as connection:
            cursor = connection.cursor()
            chats = next(cursor.execute("SELECT COUNT(*) AS n FROM _chat"))["n"]
            messages = next(cursor.execute("SELECT COUNT(*) AS n FROM _message"))["n"]
            newest = next(cursor.execute("SELECT MAX(_createdTime) AS ts FROM _message"))["ts"]
        modified = self.database.modified_at() if hasattr(self.database, "modified_at") else None
        return {
            "connected": True,
            "read_only": True,
            "chat_count": chats,
            "message_count": messages,
            "newest_message_at": _iso_time(newest),
            "database_modified_at": _iso_time(int(modified * 1000)) if modified else None,
            "sensitive_text_redaction": self.redact_sensitive,
        }

    def list_chats(
        self,
        *,
        limit: int = 20,
        unread_only: bool = False,
        updated_after: str | None = None,
        name_contains: str | None = None,
        include_official: bool = False,
    ) -> dict[str, Any]:
        limit = max(1, min(limit, 200))
        cutoff = _to_millis(updated_after)
        with self.database.connection() as connection:
            cursor = connection.cursor()
            contacts, groups, rooms, official_ids = self._name_maps(cursor)
            clauses: list[str] = []
            params: list[Any] = []
            if unread_only:
                clauses.append("_unreadCount > 0")
            if cutoff is not None:
                clauses.append("_lastUpdatedTime >= ?")
                params.append(cutoff)
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            rows = list(
                cursor.execute(
                    f"""
                    SELECT _id, _midType, _lastUpdatedTime, _unreadCount
                    FROM _chat {where}
                    ORDER BY _lastUpdatedTime DESC
                    LIMIT ?
                    """,
                    (*params, min(limit * 8, 1600)),
                )
            )

        chats: list[dict[str, Any]] = []
        needle = name_contains.casefold() if name_contains else None
        for row in rows:
            chat_id = row["_id"]
            name = self._chat_name(chat_id, row["_midType"], contacts, groups, rooms)
            is_official = row["_midType"] == 0 and chat_id in official_ids
            if is_official and not include_official:
                continue
            if needle and needle not in name.casefold():
                continue
            chats.append(
                {
                    "chat_id": chat_id,
                    "name": name,
                    "type": _chat_type(row["_midType"]),
                    "updated_at": _iso_time(row["_lastUpdatedTime"]),
                    "unread_count": row["_unreadCount"] or 0,
                    "is_official": is_official,
                }
            )
            if len(chats) >= limit:
                break
        return {"chats": chats, "count": len(chats)}

    def _format_messages(
        self,
        rows: list[dict[str, Any]],
        *,
        me: str | None,
        contacts: dict[str, str],
        groups: dict[str, str],
        rooms: dict[str, str],
        official_ids: set[str],
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for row in rows:
            text, was_redacted = self._safe_text(_message_text(row))
            chat_id = row["_chatId"]
            sender_id = row.get("_from")
            messages.append(
                {
                    "message_id": row["_id"],
                    "chat_id": chat_id,
                    "chat_name": self._chat_name(chat_id, row["_midType"], contacts, groups, rooms),
                    "chat_type": _chat_type(row["_midType"]),
                    "is_official": row["_midType"] == 0 and chat_id in official_ids,
                    "sent_at": _iso_time(row["_createdTime"]),
                    "sender_name": "Me" if sender_id == me else contacts.get(sender_id, sender_id or "Unknown"),
                    "from_me": sender_id == me,
                    "text": text,
                    "content_type": row.get("_contentType"),
                    "redacted": was_redacted,
                }
            )
        return messages

    def get_messages(
        self,
        chat_id: str,
        *,
        limit: int = 50,
        after: str | None = None,
        before: str | None = None,
    ) -> dict[str, Any]:
        limit = max(1, min(limit, 500))
        clauses = ["m._chatId = ?"]
        params: list[Any] = [chat_id]
        after_ms = _to_millis(after)
        before_ms = _to_millis(before)
        if after_ms is not None:
            clauses.append("m._createdTime >= ?")
            params.append(after_ms)
        if before_ms is not None:
            clauses.append("m._createdTime < ?")
            params.append(before_ms)
        with self.database.connection() as connection:
            cursor = connection.cursor()
            me = self._profile_mid(cursor)
            contacts, groups, rooms, official_ids = self._name_maps(cursor)
            rows = list(
                cursor.execute(
                    f"""
                    SELECT m._id, m._chatId, m._from, m._createdTime, m._text,
                           m._contentPreview, m._contentMetadata, m._contentType, c._midType
                    FROM _message m JOIN _chat c ON c._id = m._chatId
                    WHERE {' AND '.join(clauses)}
                    ORDER BY m._createdTime DESC
                    LIMIT ?
                    """,
                    (*params, limit),
                )
            )
        rows.reverse()
        messages = self._format_messages(
            rows,
            me=me,
            contacts=contacts,
            groups=groups,
            rooms=rooms,
            official_ids=official_ids,
        )
        return {"chat_id": chat_id, "messages": messages, "count": len(messages)}

    def search_messages(
        self,
        query: str,
        *,
        limit: int = 50,
        chat_id: str | None = None,
        after: str | None = None,
        before: str | None = None,
        include_official: bool = False,
    ) -> dict[str, Any]:
        query = query.strip()
        if not query:
            raise ValueError("query must not be empty")
        limit = max(1, min(limit, 200))
        clauses = ["(m._text LIKE ? ESCAPE '\\' OR m._contentPreview LIKE ? ESCAPE '\\')"]
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        params: list[Any] = [pattern, pattern]
        if chat_id:
            clauses.append("m._chatId = ?")
            params.append(chat_id)
        after_ms = _to_millis(after)
        before_ms = _to_millis(before)
        if after_ms is not None:
            clauses.append("m._createdTime >= ?")
            params.append(after_ms)
        if before_ms is not None:
            clauses.append("m._createdTime < ?")
            params.append(before_ms)
        with self.database.connection() as connection:
            cursor = connection.cursor()
            me = self._profile_mid(cursor)
            contacts, groups, rooms, official_ids = self._name_maps(cursor)
            rows = list(
                cursor.execute(
                    f"""
                    SELECT m._id, m._chatId, m._from, m._createdTime, m._text,
                           m._contentPreview, m._contentMetadata, m._contentType, c._midType
                    FROM _message m JOIN _chat c ON c._id = m._chatId
                    WHERE {' AND '.join(clauses)}
                    ORDER BY m._createdTime DESC
                    LIMIT ?
                    """,
                    (*params, min(limit * 8, 1600)),
                )
            )
        if not include_official:
            rows = [
                row
                for row in rows
                if not (row["_midType"] == 0 and row["_chatId"] in official_ids)
            ]
        rows = rows[:limit]
        messages = self._format_messages(
            rows,
            me=me,
            contacts=contacts,
            groups=groups,
            rooms=rooms,
            official_ids=official_ids,
        )
        return {"query": query, "messages": messages, "count": len(messages)}

    def recent_activity(
        self,
        *,
        hours: int = 24,
        chat_limit: int = 30,
        messages_per_chat: int = 20,
        include_official: bool = False,
    ) -> dict[str, Any]:
        hours = max(1, min(hours, 24 * 31))
        chat_limit = max(1, min(chat_limit, 100))
        messages_per_chat = max(1, min(messages_per_chat, 100))
        cutoff = datetime.now().astimezone() - timedelta(hours=hours)
        after = cutoff.isoformat()
        cutoff_ms = int(cutoff.timestamp() * 1000)
        with self.database.connection() as connection:
            cursor = connection.cursor()
            me = self._profile_mid(cursor)
            contacts, groups, rooms, official_ids = self._name_maps(cursor)
            candidate_rows = list(
                cursor.execute(
                    """
                    SELECT _id, _midType, _lastUpdatedTime, _unreadCount
                    FROM _chat
                    WHERE _lastUpdatedTime >= ?
                    ORDER BY _lastUpdatedTime DESC
                    LIMIT ?
                    """,
                    (cutoff_ms, min(chat_limit * 8, 1600)),
                )
            )
            candidate_chats = []
            for row in candidate_rows:
                is_official = row["_midType"] == 0 and row["_id"] in official_ids
                if is_official and not include_official:
                    continue
                candidate_chats.append(
                    {
                        "chat_id": row["_id"],
                        "name": self._chat_name(row["_id"], row["_midType"], contacts, groups, rooms),
                        "type": _chat_type(row["_midType"]),
                        "updated_at": _iso_time(row["_lastUpdatedTime"]),
                        "unread_count": row["_unreadCount"] or 0,
                        "is_official": is_official,
                    }
                )
                if len(candidate_chats) >= chat_limit:
                    break

            grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
            chat_ids = [chat["chat_id"] for chat in candidate_chats]
            if chat_ids:
                placeholders = ",".join("?" for _ in chat_ids)
                message_rows = list(
                    cursor.execute(
                        f"""
                        WITH ranked AS (
                          SELECT m._id, m._chatId, m._from, m._createdTime, m._text,
                                 m._contentPreview, m._contentMetadata, m._contentType, c._midType,
                                 ROW_NUMBER() OVER (
                                   PARTITION BY m._chatId ORDER BY m._createdTime DESC
                                 ) AS message_rank
                          FROM _message m JOIN _chat c ON c._id = m._chatId
                          WHERE m._createdTime >= ? AND m._chatId IN ({placeholders})
                        )
                        SELECT * FROM ranked
                        WHERE message_rank <= ?
                        ORDER BY _createdTime ASC
                        """,
                        (cutoff_ms, *chat_ids, messages_per_chat),
                    )
                )
                for row in message_rows:
                    grouped_rows[row["_chatId"]].append(row)

            activity = []
            for chat in candidate_chats:
                rows = grouped_rows.get(chat["chat_id"], [])
                if not rows:
                    continue
                messages = self._format_messages(
                    rows,
                    me=me,
                    contacts=contacts,
                    groups=groups,
                    rooms=rooms,
                    official_ids=official_ids,
                )
                activity.append({**chat, "messages": messages})
        return {
            "since": after,
            "hours": hours,
            "chats": activity,
            "chat_count": len(activity),
        }
