from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    model_validator,
)

SCHEMA_VERSION = "1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StatusResponse(StrictModel):
    connected: Literal[True]
    read_only: Literal[True]
    chat_count: NonNegativeInt
    message_count: NonNegativeInt
    newest_message_at: AwareDatetime | None
    database_modified_at: AwareDatetime | None
    sensitive_text_redaction: bool


class ChatSummary(StrictModel):
    chat_id: str
    name: str
    type: Literal["direct", "room", "group", "other"]
    updated_at: AwareDatetime | None
    unread_count: NonNegativeInt
    is_official: bool


class ListChatsResponse(StrictModel):
    chats: list[ChatSummary]
    count: NonNegativeInt


class Message(StrictModel):
    message_id: str
    chat_id: str
    chat_name: str
    chat_type: Literal["direct", "room", "group", "other"]
    is_official: bool
    sent_at: AwareDatetime | None
    sender_name: str
    from_me: bool
    text: str
    content_type: int | None
    redacted: bool


class GetMessagesResponse(StrictModel):
    chat_id: str
    messages: list[Message]
    count: NonNegativeInt


class SearchMessagesResponse(StrictModel):
    query: str
    messages: list[Message]
    count: NonNegativeInt


class ActivityChat(ChatSummary):
    messages: list[Message]


class RecentActivityResponse(StrictModel):
    since: AwareDatetime
    hours: int = Field(ge=1, le=744)
    chats: list[ActivityChat]
    chat_count: NonNegativeInt


class ToolErrorDetail(StrictModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    message: str
    retryable: bool
    suggested_action: str | None = None


DataT = TypeVar("DataT")


class ToolOutput(StrictModel, Generic[DataT]):
    schema_version: Literal["1"] = SCHEMA_VERSION
    ok: bool
    data: DataT | None = None
    error: ToolErrorDetail | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> ToolOutput[DataT]:
        if self.ok and (self.data is None or self.error is not None):
            raise ValueError("successful tool output requires data and forbids error")
        if not self.ok and (self.error is None or self.data is not None):
            raise ValueError("failed tool output requires error and forbids data")
        return self


class StatusToolOutput(ToolOutput[StatusResponse]):
    pass


class ListChatsToolOutput(ToolOutput[ListChatsResponse]):
    pass


class GetMessagesToolOutput(ToolOutput[GetMessagesResponse]):
    pass


class SearchMessagesToolOutput(ToolOutput[SearchMessagesResponse]):
    pass


class RecentActivityToolOutput(ToolOutput[RecentActivityResponse]):
    pass
