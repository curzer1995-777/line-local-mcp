from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .repository import LineRepository


READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)


def create_server(repository: LineRepository | None = None, *, host: str = "127.0.0.1", port: int = 8765) -> FastMCP:
    repo = repository or LineRepository()
    server = FastMCP(
        "line-local-mcp",
        instructions=(
            "Read-only access to the user's local LINE Desktop history. "
            "Use list_chats to resolve chat IDs, get_messages for a conversation, "
            "search_messages for text lookup, and get_recent_activity for briefs. "
            "Official accounts are excluded by default. Never claim this server can send or modify LINE messages."
        ),
        host=host,
        port=port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
    )

    @server.tool(
        name="line_status",
        title="Check LINE connection",
        description="Check whether the local LINE Desktop database is readable and how fresh it is.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def line_status() -> dict[str, Any]:
        return repo.status()

    @server.tool(
        name="list_chats",
        title="List LINE chats",
        description=(
            "Find recent LINE conversations and their stable chat IDs. Use before get_messages when the chat ID is unknown. "
            "Official accounts are excluded unless explicitly requested."
        ),
        annotations=READ_ONLY,
        structured_output=True,
    )
    def list_chats(
        limit: Annotated[int, Field(ge=1, le=200, description="Maximum chats to return.")] = 20,
        unread_only: Annotated[bool, Field(description="Only return chats with unread messages.")] = False,
        updated_after: Annotated[
            str | None,
            Field(description="Only chats updated at or after this ISO 8601 timestamp."),
        ] = None,
        name_contains: Annotated[
            str | None,
            Field(description="Case-insensitive substring of the chat name."),
        ] = None,
        include_official: Annotated[
            bool,
            Field(description="Include LINE official/business accounts. Defaults to false."),
        ] = False,
    ) -> dict[str, Any]:
        return repo.list_chats(
            limit=limit,
            unread_only=unread_only,
            updated_after=updated_after,
            name_contains=name_contains,
            include_official=include_official,
        )

    @server.tool(
        name="get_messages",
        title="Read a LINE conversation",
        description="Read both sides of one LINE conversation by chat ID, ordered oldest to newest.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def get_messages(
        chat_id: Annotated[str, Field(min_length=1, description="Chat ID returned by list_chats.")],
        limit: Annotated[int, Field(ge=1, le=500, description="Maximum messages to return.")] = 50,
        after: Annotated[str | None, Field(description="ISO 8601 inclusive lower time bound.")] = None,
        before: Annotated[str | None, Field(description="ISO 8601 exclusive upper time bound.")] = None,
    ) -> dict[str, Any]:
        return repo.get_messages(chat_id, limit=limit, after=after, before=before)

    @server.tool(
        name="search_messages",
        title="Search LINE messages",
        description=(
            "Search message text across both sent and received LINE messages. "
            "Optionally restrict by chat and time. Official accounts are excluded by default."
        ),
        annotations=READ_ONLY,
        structured_output=True,
    )
    def search_messages(
        query: Annotated[str, Field(min_length=1, description="Literal text to find.")],
        limit: Annotated[int, Field(ge=1, le=200, description="Maximum matching messages.")] = 50,
        chat_id: Annotated[str | None, Field(description="Optional chat ID restriction.")] = None,
        after: Annotated[str | None, Field(description="ISO 8601 inclusive lower time bound.")] = None,
        before: Annotated[str | None, Field(description="ISO 8601 exclusive upper time bound.")] = None,
        include_official: Annotated[bool, Field(description="Include official/business accounts.")] = False,
    ) -> dict[str, Any]:
        return repo.search_messages(
            query,
            limit=limit,
            chat_id=chat_id,
            after=after,
            before=before,
            include_official=include_official,
        )

    @server.tool(
        name="get_recent_activity",
        title="Read recent LINE activity",
        description=(
            "Return recent conversations with both sides of their messages, grouped by chat. "
            "Use this for daily or weekly briefs. Official accounts are excluded by default."
        ),
        annotations=READ_ONLY,
        structured_output=True,
    )
    def get_recent_activity(
        hours: Annotated[int, Field(ge=1, le=744, description="Lookback window in hours.")] = 24,
        chat_limit: Annotated[int, Field(ge=1, le=100, description="Maximum conversations.")] = 30,
        messages_per_chat: Annotated[int, Field(ge=1, le=100, description="Maximum messages per conversation.")] = 20,
        include_official: Annotated[bool, Field(description="Include official/business accounts.")] = False,
    ) -> dict[str, Any]:
        return repo.recent_activity(
            hours=hours,
            chat_limit=chat_limit,
            messages_per_chat=messages_per_chat,
            include_official=include_official,
        )

    return server
