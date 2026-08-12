from __future__ import annotations


def test_list_chats_excludes_official_by_default(repository):
    result = repository.list_chats(limit=10)
    assert [chat["name"] for chat in result["chats"]] == ["Project Team", "Alice"]
    assert result["chats"][1]["unread_count"] == 1


def test_list_chats_can_include_official(repository):
    result = repository.list_chats(limit=10, include_official=True)
    assert result["chats"][0]["name"] == "Shop News"
    assert result["chats"][0]["is_official"] is True


def test_get_messages_reads_both_sides_and_redacts(repository):
    result = repository.get_messages("alice", limit=10)
    assert [message["from_me"] for message in result["messages"]] == [False, True]
    assert result["messages"][1]["text"] == "Yes. password: [REDACTED]"
    assert result["messages"][1]["redacted"] is True


def test_search_messages_excludes_official(repository):
    result = repository.search_messages("Project", limit=10)
    assert [message["message_id"] for message in result["messages"]] == ["m3"]


def test_search_treats_wildcards_as_literal(repository):
    assert repository.search_messages("%", limit=10)["count"] == 0


def test_recent_activity_groups_messages(repository):
    result = repository.recent_activity(hours=744, chat_limit=10, messages_per_chat=10)
    assert {chat["name"] for chat in result["chats"]} == {"Alice", "Project Team"}
