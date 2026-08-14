from __future__ import annotations

import apsw


def test_index_seek_newest_timestamp_matches_full_message_scan(repository):
    with repository.database.connection() as connection:
        cursor = connection.cursor()
        expected = next(cursor.execute("SELECT MAX(_createdTime) AS ts FROM _message"))[
            "ts"
        ]
        actual = repository._load_source_newest_message_at(cursor)

    assert actual == expected


def test_list_chats_excludes_official_by_default(repository):
    result = repository.list_chats(limit=10)
    assert [chat["name"] for chat in result["chats"]] == ["Project Team", "Alice"]
    assert result["chats"][1]["unread_count"] == 1
    assert result["total_matched"] == 2
    assert result["has_more"] is False


def test_list_chats_reports_when_results_are_limited(repository):
    result = repository.list_chats(limit=1)
    assert result["count"] == 1
    assert result["total_matched"] == 2
    assert result["has_more"] is True


def test_list_chats_name_filter_does_not_miss_matches_beyond_old_candidate_cap(
    repository,
):
    database = apsw.Connection(str(repository.database.path))
    cursor = database.cursor()
    cursor.executemany(
        "INSERT INTO _contact VALUES (?, ?, ?)",
        [(f"extra-{index}", f"Extra {index}", 0) for index in range(200)],
    )
    cursor.executemany(
        "INSERT INTO _chat VALUES (?, ?, ?, ?)",
        [(f"extra-{index}", 0, 1_900_000_000_000 + index, 0) for index in range(200)],
    )
    cursor.execute(
        "INSERT INTO _contact VALUES (?, ?, ?)",
        ("older-match", "Needle Customer", 0),
    )
    cursor.execute(
        "INSERT INTO _chat VALUES (?, ?, ?, ?)",
        ("older-match", 0, 1_700_000_000_000, 0),
    )
    database.close()

    result = repository.list_chats(limit=20, name_contains="Needle")

    assert [chat["name"] for chat in result["chats"]] == ["Needle Customer"]
    assert result["total_matched"] == 1


def test_list_chats_can_include_official(repository):
    result = repository.list_chats(limit=10, include_official=True)
    assert result["chats"][0]["name"] == "Shop News"
    assert result["chats"][0]["is_official"] is True


def test_get_messages_reads_both_sides_and_redacts(repository):
    result = repository.get_messages("alice", limit=10)
    assert [message["from_me"] for message in result["messages"]] == [False, True]
    assert result["messages"][1]["text"] == "Yes. password: [REDACTED]"
    assert result["messages"][1]["text_source"] == "text"
    assert result["messages"][1]["redacted"] is True
    assert result["total_matched"] == 2
    assert result["has_more"] is False


def test_get_messages_reports_coverage_when_limited(repository):
    result = repository.get_messages("alice", limit=1)
    assert [message["message_id"] for message in result["messages"]] == ["m2"]
    assert result["total_matched"] == 2
    assert result["has_more"] is True


def test_get_messages_returns_safe_content_metadata_without_urls(repository):
    result = repository.get_messages("group-1", limit=10)
    image = result["messages"][1]
    assert image["text"] == "Campaign image"
    assert image["text_source"] == "metadata"
    assert image["content_metadata"] == {
        "alt_text": "Campaign image",
        "file_size_bytes": 2048,
        "width": 1200,
        "height": 630,
        "download_available": True,
        "preview_available": False,
    }
    assert "example.invalid" not in str(image)


def test_search_messages_excludes_official(repository):
    result = repository.search_messages("Project", limit=10)
    assert [message["message_id"] for message in result["messages"]] == ["m3"]
    assert result["total_matched"] == 1
    assert result["has_more"] is False


def test_search_messages_finds_safe_metadata_text(repository):
    result = repository.search_messages("Campaign image", limit=10)
    assert [message["message_id"] for message in result["messages"]] == ["m5"]


def test_search_treats_wildcards_as_literal(repository):
    assert repository.search_messages("%", limit=10)["count"] == 0


def test_recent_activity_groups_messages(repository):
    result = repository.recent_activity(hours=744, chat_limit=10, messages_per_chat=10)
    assert {chat["name"] for chat in result["chats"]} == {"Alice", "Project Team"}


def test_activity_uses_message_time_when_chat_update_time_is_stale(repository):
    database = apsw.Connection(str(repository.database.path))
    database.cursor().execute(
        "UPDATE _chat SET _lastUpdatedTime = 1 WHERE _id IN ('alice', 'group-1')"
    )
    database.close()

    result = repository._activity_window(
        after_ms=1_786_499_900_000,
        before_ms=1_786_500_300_000,
        name_contains=None,
        chat_limit=10,
        messages_per_chat=10,
        include_official=False,
    )

    assert [chat["name"] for chat in result["chats"]] == ["Project Team", "Alice"]
    assert result["total_matched_chats"] == 2


def test_read_chat_activity_resolves_name_and_reports_per_chat_coverage(repository):
    result = repository.read_chat_activity(
        "project",
        after="2020-01-01T00:00:00+00:00",
        before="2030-01-01T00:00:00+00:00",
        messages_per_chat=1,
    )
    assert result["total_matched_chats"] == 1
    assert result["source_newest_message_at"] is not None
    assert result["has_more_chats"] is False
    assert result["chats"][0]["name"] == "Project Team"
    assert result["chats"][0]["message_count"] == 1
    assert result["chats"][0]["total_matched_messages"] == 2
    assert result["chats"][0]["messages_have_more"] is True
    assert result["chats"][0]["messages"][0]["message_id"] == "m5"
