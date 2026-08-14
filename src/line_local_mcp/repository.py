from __future__ import annotations

import json
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from .config import Settings
from .database import ConnectionProvider, LineDatabase
from .redaction import redact_text

NameMaps = tuple[dict[str, str], dict[str, str], dict[str, str], set[str]]
ChatDirectory = list[dict[str, Any]]


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
    return (
        datetime.fromtimestamp(value / 1000).astimezone().isoformat(timespec="seconds")
    )


def _chat_type(mid_type: int | None) -> str:
    return {0: "direct", 1: "room", 2: "group"}.get(mid_type, "other")


def _metadata_dict(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("_contentMetadata")
    if not metadata:
        return {}
    try:
        parsed = json.loads(metadata)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _first_string(metadata: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            rendered = str(value).strip()
            if rendered:
                return rendered
    return None


def _nonnegative_int(metadata: dict[str, Any], *keys: str) -> int | None:
    value = _first_string(metadata, *keys)
    if value is None:
        return None
    try:
        parsed = int(float(value))
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _message_text(row: dict[str, Any], metadata: dict[str, Any]) -> tuple[str, str]:
    if row.get("_text"):
        return str(row["_text"]), "text"
    if row.get("_contentPreview"):
        return str(row["_contentPreview"]), "content_preview"
    metadata_text = _first_string(metadata, "ALT_TEXT", "altText", "text", "title")
    if metadata_text is not None:
        return metadata_text, "metadata"
    labels = {1: "[image]", 2: "[video]", 3: "[audio]", 7: "[sticker]", 14: "[file]"}
    return labels.get(row.get("_contentType"), "[non-text message]"), "placeholder"


class LineRepository:
    def __init__(
        self,
        database: ConnectionProvider | None = None,
        *,
        redact_sensitive: bool | None = None,
    ):
        settings = Settings.from_env()
        self.database = database or LineDatabase(settings)
        self.redact_sensitive = (
            settings.redact_sensitive if redact_sensitive is None else redact_sensitive
        )
        self._name_cache_lock = threading.RLock()
        self._name_cache_token: object | None = None
        self._name_cache: NameMaps | None = None
        self._chat_cache_token: object | None = None
        self._chat_cache: ChatDirectory | None = None
        self._profile_cache_token: object | None = None
        self._profile_cache_loaded = False
        self._profile_cache: str | None = None
        self._newest_cache_token: object | None = None
        self._newest_cache_loaded = False
        self._newest_cache: int | None = None

    @staticmethod
    def _load_profile_mid(cursor: Any) -> str | None:
        row = next(cursor.execute("SELECT _mid FROM _profile LIMIT 1"), None)
        return row["_mid"] if row else None

    def _profile_mid(self, cursor: Any, cache_token: object | None) -> str | None:
        if cache_token is None:
            return self._load_profile_mid(cursor)
        with self._name_cache_lock:
            if self._profile_cache_token == cache_token and self._profile_cache_loaded:
                return self._profile_cache
            loaded = self._load_profile_mid(cursor)
            self._profile_cache_token = cache_token
            self._profile_cache_loaded = True
            self._profile_cache = loaded
            return loaded

    @staticmethod
    def _load_source_newest_message_at(cursor: Any) -> int | None:
        return next(
            cursor.execute(
                """
                SELECT MAX((
                  SELECT MAX(message._createdTime)
                  FROM _message message
                  WHERE message._chatId = chat._id
                )) AS ts
                FROM _chat chat
                """
            )
        )["ts"]

    def _source_newest_message_at(
        self, cursor: Any, cache_token: object | None
    ) -> int | None:
        if cache_token is None:
            return self._load_source_newest_message_at(cursor)
        with self._name_cache_lock:
            if self._newest_cache_token == cache_token and self._newest_cache_loaded:
                return self._newest_cache
            loaded = self._load_source_newest_message_at(cursor)
            self._newest_cache_token = cache_token
            self._newest_cache_loaded = True
            self._newest_cache = loaded
            return loaded

    @staticmethod
    def _load_name_maps(
        cursor: Any,
    ) -> NameMaps:
        contacts: dict[str, str] = {}
        official: set[str] = set()
        for row in cursor.execute(
            "SELECT _mid, _displayName, _capableBuddy FROM _contact"
        ):
            contacts[row["_mid"]] = row["_displayName"] or row["_mid"]
            if row["_capableBuddy"] == 1:
                official.add(row["_mid"])
        groups = {
            row["_chatMid"]: row["_chatName"] or row["_chatMid"]
            for row in cursor.execute("SELECT _chatMid, _chatName FROM _groupChat")
        }
        rooms = {
            row["_mid"]: row["_mid"] for row in cursor.execute("SELECT _mid FROM _room")
        }
        return contacts, groups, rooms, official

    def _name_maps(self, cursor: Any, cache_token: object | None) -> NameMaps:
        if cache_token is None:
            return self._load_name_maps(cursor)
        with self._name_cache_lock:
            if self._name_cache_token == cache_token and self._name_cache is not None:
                return self._name_cache
            loaded = self._load_name_maps(cursor)
            self._name_cache_token = cache_token
            self._name_cache = loaded
            return loaded

    def _load_chat_directory(self, cursor: Any, name_maps: NameMaps) -> ChatDirectory:
        contacts, groups, rooms, official_ids = name_maps
        directory: ChatDirectory = []
        for row in cursor.execute(
            """
            SELECT _id, _midType, _lastUpdatedTime, _unreadCount
            FROM _chat
            ORDER BY _lastUpdatedTime DESC
            """
        ):
            chat_id = row["_id"]
            directory.append(
                {
                    "chat_id": chat_id,
                    "name": self._chat_name(
                        chat_id, row["_midType"], contacts, groups, rooms
                    ),
                    "mid_type": row["_midType"],
                    "updated_at_ms": row["_lastUpdatedTime"],
                    "unread_count": row["_unreadCount"] or 0,
                    "is_official": row["_midType"] == 0 and chat_id in official_ids,
                }
            )
        return directory

    def _chat_directory(
        self, cursor: Any, cache_token: object | None, name_maps: NameMaps
    ) -> ChatDirectory:
        if cache_token is None:
            return self._load_chat_directory(cursor, name_maps)
        with self._name_cache_lock:
            if self._chat_cache_token == cache_token and self._chat_cache is not None:
                return self._chat_cache
            loaded = self._load_chat_directory(cursor, name_maps)
            self._chat_cache_token = cache_token
            self._chat_cache = loaded
            return loaded

    @staticmethod
    def _public_chat(chat: dict[str, Any]) -> dict[str, Any]:
        return {
            "chat_id": chat["chat_id"],
            "name": chat["name"],
            "type": _chat_type(chat["mid_type"]),
            "updated_at": _iso_time(chat["updated_at_ms"]),
            "unread_count": chat["unread_count"],
            "is_official": chat["is_official"],
        }

    @staticmethod
    def _cache_token(connection: Any) -> object | None:
        return getattr(connection, "cache_token", None)

    @staticmethod
    def _snapshot_id(connection: Any) -> str | None:
        return getattr(connection, "snapshot_id", None)

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

    def _safe_content_metadata(
        self, metadata: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, bool]:
        result: dict[str, Any] = {}
        was_redacted = False
        text_fields = {
            "alt_text": _first_string(metadata, "ALT_TEXT", "altText"),
            "metadata_text": _first_string(metadata, "text", "title"),
            "file_name": _first_string(metadata, "FILE_NAME"),
        }
        for field, value in text_fields.items():
            if value is None:
                continue
            safe_value, field_redacted = self._safe_text(value)
            result[field] = safe_value
            was_redacted = was_redacted or field_redacted

        numeric_fields = {
            "file_size_bytes": _nonnegative_int(metadata, "FILE_SIZE"),
            "duration_ms": _nonnegative_int(metadata, "DURATION"),
            "width": _nonnegative_int(metadata, "width", "WIDTH"),
            "height": _nonnegative_int(metadata, "height", "HEIGHT"),
        }
        result.update(
            {
                field: value
                for field, value in numeric_fields.items()
                if value is not None
            }
        )
        media_type = _first_string(metadata, "mediaType", "contentType")
        if media_type is not None:
            result["media_type"] = media_type

        if not result and not any(
            metadata.get(key)
            for key in ("DOWNLOAD_URL", "PREVIEW_URL", "downloadUrl", "previewUrl")
        ):
            return None, was_redacted
        result["download_available"] = bool(
            metadata.get("DOWNLOAD_URL") or metadata.get("downloadUrl")
        )
        result["preview_available"] = bool(
            metadata.get("PREVIEW_URL") or metadata.get("previewUrl")
        )
        return result, was_redacted

    def status(self) -> dict[str, Any]:
        with self.database.connection() as connection:
            cursor = connection.cursor()
            snapshot_id = self._snapshot_id(connection)
            cache_token = self._cache_token(connection)
            chats = next(cursor.execute("SELECT COUNT(*) AS n FROM _chat"))["n"]
            messages = next(cursor.execute("SELECT COUNT(*) AS n FROM _message"))["n"]
            newest = self._source_newest_message_at(cursor, cache_token)
        modified = (
            self.database.modified_at()
            if hasattr(self.database, "modified_at")
            else None
        )
        return {
            "connected": True,
            "read_only": True,
            "chat_count": chats,
            "message_count": messages,
            "newest_message_at": _iso_time(newest),
            "database_modified_at": _iso_time(int(modified * 1000))
            if modified
            else None,
            "sensitive_text_redaction": self.redact_sensitive,
            "snapshot_id": snapshot_id,
            "snapshot_cache": self.database.cache_info()
            if hasattr(self.database, "cache_info")
            else None,
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
            snapshot_id = self._snapshot_id(connection)
            cache_token = self._cache_token(connection)
            name_maps = self._name_maps(cursor, cache_token)
            directory = self._chat_directory(cursor, cache_token, name_maps)

        matched_chats: list[dict[str, Any]] = []
        needle = name_contains.casefold() if name_contains else None
        for chat in directory:
            if unread_only and chat["unread_count"] == 0:
                continue
            if cutoff is not None and chat["updated_at_ms"] < cutoff:
                continue
            if chat["is_official"] and not include_official:
                continue
            if needle and needle not in chat["name"].casefold():
                continue
            matched_chats.append(self._public_chat(chat))
        chats = matched_chats[:limit]
        return {
            "chats": chats,
            "count": len(chats),
            "total_matched": len(matched_chats),
            "has_more": len(matched_chats) > len(chats),
            "snapshot_id": snapshot_id,
        }

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
            raw_metadata = _metadata_dict(row)
            raw_text, text_source = _message_text(row, raw_metadata)
            text, text_redacted = self._safe_text(raw_text)
            content_metadata, metadata_redacted = self._safe_content_metadata(
                raw_metadata
            )
            chat_id = row["_chatId"]
            sender_id = row.get("_from")
            messages.append(
                {
                    "message_id": row["_id"],
                    "chat_id": chat_id,
                    "chat_name": self._chat_name(
                        chat_id, row["_midType"], contacts, groups, rooms
                    ),
                    "chat_type": _chat_type(row["_midType"]),
                    "is_official": row["_midType"] == 0 and chat_id in official_ids,
                    "sent_at": _iso_time(row["_createdTime"]),
                    "sender_name": "Me"
                    if sender_id == me
                    else contacts.get(sender_id, sender_id or "Unknown"),
                    "from_me": sender_id == me,
                    "text": text,
                    "text_source": text_source,
                    "content_type": row.get("_contentType"),
                    "content_metadata": content_metadata,
                    "redacted": text_redacted or metadata_redacted,
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
            snapshot_id = self._snapshot_id(connection)
            cache_token = self._cache_token(connection)
            me = self._profile_mid(cursor, cache_token)
            contacts, groups, rooms, official_ids = self._name_maps(cursor, cache_token)
            rows = list(
                cursor.execute(
                    f"""
                    SELECT m._id, m._chatId, m._from, m._createdTime, m._text,
                           m._contentPreview, m._contentMetadata, m._contentType, c._midType,
                           COUNT(*) OVER () AS total_count
                    FROM _message m JOIN _chat c ON c._id = m._chatId
                    WHERE {" AND ".join(clauses)}
                    ORDER BY m._createdTime DESC, m._id DESC
                    LIMIT ?
                    """,
                    (*params, limit),
                )
            )
            total_matched = rows[0]["total_count"] if rows else 0
        rows.reverse()
        messages = self._format_messages(
            rows,
            me=me,
            contacts=contacts,
            groups=groups,
            rooms=rooms,
            official_ids=official_ids,
        )
        return {
            "chat_id": chat_id,
            "messages": messages,
            "count": len(messages),
            "total_matched": total_matched,
            "has_more": total_matched > len(messages),
            "snapshot_id": snapshot_id,
        }

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
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        searchable_metadata = (
            "CASE WHEN json_valid(m._contentMetadata) "
            "THEN COALESCE(json_extract(m._contentMetadata, '$.ALT_TEXT'), '') || ' ' || "
            "COALESCE(json_extract(m._contentMetadata, '$.altText'), '') || ' ' || "
            "COALESCE(json_extract(m._contentMetadata, '$.text'), '') || ' ' || "
            "COALESCE(json_extract(m._contentMetadata, '$.title'), '') ELSE '' END"
        )
        clauses = [
            (
                f"(m._text LIKE ? ESCAPE '\\' OR m._contentPreview LIKE ? ESCAPE '\\' "
                f"OR {searchable_metadata} LIKE ? ESCAPE '\\')"
            )
        ]
        params: list[Any] = [pattern, pattern, pattern]
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
        if not include_official:
            clauses.append(
                "NOT (c._midType = 0 AND EXISTS ("
                "SELECT 1 FROM _contact official_contact "
                "WHERE official_contact._mid = m._chatId "
                "AND official_contact._capableBuddy = 1))"
            )
        with self.database.connection() as connection:
            cursor = connection.cursor()
            snapshot_id = self._snapshot_id(connection)
            cache_token = self._cache_token(connection)
            me = self._profile_mid(cursor, cache_token)
            contacts, groups, rooms, official_ids = self._name_maps(cursor, cache_token)
            rows = list(
                cursor.execute(
                    f"""
                    SELECT m._id, m._chatId, m._from, m._createdTime, m._text,
                           m._contentPreview, m._contentMetadata, m._contentType, c._midType,
                           COUNT(*) OVER () AS total_count
                    FROM _message m JOIN _chat c ON c._id = m._chatId
                    WHERE {" AND ".join(clauses)}
                    ORDER BY m._createdTime DESC, m._id DESC
                    LIMIT ?
                    """,
                    (*params, limit),
                )
            )
            total_matched = rows[0]["total_count"] if rows else 0
        messages = self._format_messages(
            rows,
            me=me,
            contacts=contacts,
            groups=groups,
            rooms=rooms,
            official_ids=official_ids,
        )
        return {
            "query": query,
            "messages": messages,
            "count": len(messages),
            "total_matched": total_matched,
            "has_more": total_matched > len(messages),
            "snapshot_id": snapshot_id,
        }

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
        activity = self._activity_window(
            after_ms=int(cutoff.timestamp() * 1000),
            before_ms=None,
            name_contains=None,
            chat_limit=chat_limit,
            messages_per_chat=messages_per_chat,
            include_official=include_official,
        )
        return {"since": after, "hours": hours, **activity}

    def read_chat_activity(
        self,
        name_contains: str,
        *,
        after: str,
        before: str,
        chat_limit: int = 20,
        messages_per_chat: int = 200,
        include_official: bool = False,
    ) -> dict[str, Any]:
        name_contains = name_contains.strip()
        if not name_contains:
            raise ValueError("name_contains must not be empty")
        chat_limit = max(1, min(chat_limit, 100))
        messages_per_chat = max(1, min(messages_per_chat, 500))
        after_ms = _to_millis(after)
        before_ms = _to_millis(before)
        if after_ms is None or before_ms is None:
            raise ValueError("after and before are required")
        activity = self._activity_window(
            after_ms=after_ms,
            before_ms=before_ms,
            name_contains=name_contains,
            chat_limit=chat_limit,
            messages_per_chat=messages_per_chat,
            include_official=include_official,
        )
        return {
            "name_contains": name_contains,
            "after": _iso_time(after_ms),
            "before": _iso_time(before_ms),
            **activity,
        }

    def _activity_window(
        self,
        *,
        after_ms: int,
        before_ms: int | None,
        name_contains: str | None,
        chat_limit: int,
        messages_per_chat: int,
        include_official: bool,
    ) -> dict[str, Any]:
        with self.database.connection() as connection:
            cursor = connection.cursor()
            snapshot_id = self._snapshot_id(connection)
            cache_token = self._cache_token(connection)
            me = self._profile_mid(cursor, cache_token)
            name_maps = self._name_maps(cursor, cache_token)
            contacts, groups, rooms, official_ids = name_maps
            directory = self._chat_directory(cursor, cache_token, name_maps)
            source_newest_message_at = self._source_newest_message_at(
                cursor, cache_token
            )
            needle = name_contains.casefold() if name_contains else None
            candidates: ChatDirectory = []
            for chat in directory:
                if chat["is_official"] and not include_official:
                    continue
                if needle and needle not in chat["name"].casefold():
                    continue
                candidates.append(chat)

            time_clauses = ["_createdTime >= ?"]
            time_params: list[Any] = [after_ms]
            if before_ms is not None:
                time_clauses.append("_createdTime < ?")
                time_params.append(before_ms)

            message_counts: dict[str, int] = {}
            latest_message_times: dict[str, int] = {}
            candidate_ids = [chat["chat_id"] for chat in candidates]
            for offset in range(0, len(candidate_ids), 500):
                id_batch = candidate_ids[offset : offset + 500]
                placeholders = ",".join("?" for _ in id_batch)
                count_rows = cursor.execute(
                    f"""
                    SELECT _chatId, COUNT(*) AS total_count,
                           MAX(_createdTime) AS latest_message_at
                    FROM _message
                    WHERE {" AND ".join(time_clauses)}
                      AND _chatId IN ({placeholders})
                    GROUP BY _chatId
                    """,
                    (*time_params, *id_batch),
                )
                for row in count_rows:
                    message_counts[row["_chatId"]] = row["total_count"]
                    latest_message_times[row["_chatId"]] = row["latest_message_at"]

            matched_chats = [
                chat
                for chat in candidates
                if message_counts.get(chat["chat_id"], 0) > 0
            ]
            matched_chats.sort(
                key=lambda chat: (
                    latest_message_times[chat["chat_id"]],
                    chat["chat_id"],
                ),
                reverse=True,
            )
            total_matched_chats = len(matched_chats)
            selected_chats = matched_chats[:chat_limit]

            grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
            chat_ids = [chat["chat_id"] for chat in selected_chats]
            if chat_ids:
                placeholders = ",".join("?" for _ in chat_ids)
                message_time_clauses = ["m._createdTime >= ?"]
                message_params: list[Any] = [after_ms]
                if before_ms is not None:
                    message_time_clauses.append("m._createdTime < ?")
                    message_params.append(before_ms)
                message_time_clauses.append(f"m._chatId IN ({placeholders})")
                message_params.extend(chat_ids)
                if all(
                    message_counts[chat_id] <= messages_per_chat for chat_id in chat_ids
                ):
                    message_sql = f"""
                        SELECT m._id, m._chatId, m._from, m._createdTime, m._text,
                               m._contentPreview, m._contentMetadata, m._contentType, c._midType
                        FROM _message m JOIN _chat c ON c._id = m._chatId
                        WHERE {" AND ".join(message_time_clauses)}
                        ORDER BY m._createdTime ASC, m._id ASC
                    """
                else:
                    message_sql = f"""
                        WITH ranked AS (
                          SELECT m._id, m._chatId, m._from, m._createdTime, m._text,
                                 m._contentPreview, m._contentMetadata, m._contentType, c._midType,
                                 ROW_NUMBER() OVER (
                                   PARTITION BY m._chatId
                                   ORDER BY m._createdTime DESC, m._id DESC
                                 ) AS message_rank
                          FROM _message m JOIN _chat c ON c._id = m._chatId
                          WHERE {" AND ".join(message_time_clauses)}
                        )
                        SELECT * FROM ranked
                        WHERE message_rank <= ?
                        ORDER BY _createdTime ASC, _id ASC
                    """
                    message_params.append(messages_per_chat)
                message_rows = list(cursor.execute(message_sql, message_params))
                for row in message_rows:
                    grouped_rows[row["_chatId"]].append(row)

            activity = []
            for chat in selected_chats:
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
                activity.append({**self._public_chat(chat), "messages": messages})
                activity[-1].update(
                    {
                        "message_count": len(messages),
                        "total_matched_messages": message_counts[chat["chat_id"]],
                        "messages_have_more": message_counts[chat["chat_id"]]
                        > len(messages),
                    }
                )
        return {
            "source_newest_message_at": _iso_time(source_newest_message_at),
            "chats": activity,
            "chat_count": len(activity),
            "total_matched_chats": total_matched_chats,
            "has_more_chats": total_matched_chats > len(selected_chats),
            "snapshot_id": snapshot_id,
        }
