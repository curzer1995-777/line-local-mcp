from __future__ import annotations

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from line_local_mcp.server import create_server


@pytest.mark.anyio
async def test_mcp_lists_tools_and_calls_repository(repository):
    server = create_server(repository)
    async with create_connected_server_and_client_session(server) as session:
        tools = await session.list_tools()
        names = {tool.name for tool in tools.tools}
        assert names == {
            "line_status",
            "list_chats",
            "get_messages",
            "search_messages",
            "get_recent_activity",
        }
        assert all(tool.annotations and tool.annotations.readOnlyHint for tool in tools.tools)

        result = await session.call_tool("get_messages", {"chat_id": "alice", "limit": 10})
        assert result.isError is False
        assert result.structuredContent["count"] == 2
