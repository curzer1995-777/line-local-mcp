from __future__ import annotations

import json

import pytest
from mcp import Client

from line_local_mcp.database import LineDatabaseError
from line_local_mcp.server import create_server


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_mcp_lists_typed_read_only_tools_and_calls_repository(repository, mode):
    server = create_server(repository)
    async with Client(server, mode=mode) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools.tools}
        assert names == {
            "line_status",
            "list_chats",
            "get_messages",
            "search_messages",
            "get_recent_activity",
        }
        assert all(
            tool.annotations and tool.annotations.read_only_hint for tool in tools.tools
        )
        assert all(
            tool.annotations and tool.annotations.idempotent_hint
            for tool in tools.tools
        )
        assert all(tool.output_schema for tool in tools.tools)

        get_messages = next(tool for tool in tools.tools if tool.name == "get_messages")
        assert get_messages.output_schema["type"] == "object"
        assert "schema_version" in json.dumps(get_messages.output_schema)

        result = await client.call_tool(
            "get_messages", {"chat_id": "alice", "limit": 10}
        )
        assert result.is_error is False
        assert result.structured_content["schema_version"] == "1"
        assert result.structured_content["ok"] is True
        assert result.structured_content["data"]["count"] == 2
        assert json.loads(result.content[0].text) == result.structured_content


@pytest.mark.anyio
async def test_tool_validation_error_is_visible_to_model(repository):
    async with Client(create_server(repository)) as client:
        result = await client.call_tool(
            "get_messages", {"chat_id": "alice", "after": "not-a-date"}
        )

    assert result.is_error is True
    assert (
        "timezone-aware" in result.content[0].text
        or "datetime" in result.content[0].text
    )


@pytest.mark.anyio
async def test_tool_rejects_blank_search_before_repository_call(repository):
    async with Client(create_server(repository)) as client:
        result = await client.call_tool("search_messages", {"query": "   "})

    assert result.is_error is True
    assert "at least 1 character" in result.content[0].text


@pytest.mark.anyio
async def test_tool_returns_structured_recoverable_database_error():
    class FailingRepository:
        def status(self):
            raise LineDatabaseError(
                "Database is temporarily unavailable.",
                code="DATABASE_UNREADABLE",
                retryable=True,
                suggested_action="Retry after LINE finishes syncing.",
            )

    async with Client(create_server(FailingRepository())) as client:
        result = await client.call_tool("line_status", {})

    assert result.is_error is True
    assert result.structured_content == {
        "schema_version": "1",
        "ok": False,
        "error": {
            "code": "DATABASE_UNREADABLE",
            "message": "Database is temporarily unavailable.",
            "retryable": True,
            "suggested_action": "Retry after LINE finishes syncing.",
        },
    }


@pytest.mark.anyio
async def test_tool_rejects_inverted_time_window(repository):
    async with Client(create_server(repository)) as client:
        result = await client.call_tool(
            "get_messages",
            {
                "chat_id": "alice",
                "after": "2026-08-14T10:00:00+08:00",
                "before": "2026-08-14T09:00:00+08:00",
            },
        )

    assert result.is_error is True
    assert result.structured_content["error"]["code"] == "INVALID_TIME_WINDOW"


@pytest.mark.anyio
async def test_unexpected_error_does_not_expose_exception_text():
    class BrokenRepository:
        def status(self):
            raise RuntimeError("private implementation detail")

    async with Client(create_server(BrokenRepository())) as client:
        result = await client.call_tool("line_status", {})

    assert result.is_error is True
    assert result.structured_content["error"]["code"] == "INTERNAL_ERROR"
    assert "private implementation detail" not in result.content[0].text
