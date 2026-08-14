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


class SnapshotCacheStatus(StrictModel):
    enabled: bool
    ttl_seconds: float = Field(ge=0)
    hits: NonNegativeInt
    misses: NonNegativeInt
    rebuilds: NonNegativeInt
    consistency_retries: NonNegativeInt
    keychain_reads: NonNegativeInt


class StatusResponse(StrictModel):
    connected: Literal[True]
    read_only: Literal[True]
    chat_count: NonNegativeInt
    message_count: NonNegativeInt
    newest_message_at: AwareDatetime | None
    database_modified_at: AwareDatetime | None
    sensitive_text_redaction: bool
    snapshot_id: str | None = None
    snapshot_cache: SnapshotCacheStatus | None = None


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
    total_matched: NonNegativeInt
    has_more: bool
    snapshot_id: str | None = None


class MessageContentMetadata(StrictModel):
    alt_text: str | None = None
    metadata_text: str | None = None
    file_name: str | None = None
    file_size_bytes: NonNegativeInt | None = None
    duration_ms: NonNegativeInt | None = None
    width: NonNegativeInt | None = None
    height: NonNegativeInt | None = None
    media_type: str | None = None
    download_available: bool = False
    preview_available: bool = False


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
    text_source: Literal["text", "content_preview", "metadata", "placeholder"]
    content_type: int | None
    content_metadata: MessageContentMetadata | None = None
    redacted: bool


class GetMessagesResponse(StrictModel):
    chat_id: str
    messages: list[Message]
    count: NonNegativeInt
    total_matched: NonNegativeInt
    has_more: bool
    snapshot_id: str | None = None


class SearchMessagesResponse(StrictModel):
    query: str
    messages: list[Message]
    count: NonNegativeInt
    total_matched: NonNegativeInt
    has_more: bool
    snapshot_id: str | None = None


class ActivityChat(ChatSummary):
    messages: list[Message]
    message_count: NonNegativeInt
    total_matched_messages: NonNegativeInt
    messages_have_more: bool


class RecentActivityResponse(StrictModel):
    since: AwareDatetime
    hours: int = Field(ge=1, le=744)
    source_newest_message_at: AwareDatetime | None
    chats: list[ActivityChat]
    chat_count: NonNegativeInt
    total_matched_chats: NonNegativeInt
    has_more_chats: bool
    snapshot_id: str | None = None


class ChatActivityResponse(StrictModel):
    name_contains: str
    after: AwareDatetime
    before: AwareDatetime
    source_newest_message_at: AwareDatetime | None
    chats: list[ActivityChat]
    chat_count: NonNegativeInt
    total_matched_chats: NonNegativeInt
    has_more_chats: bool
    snapshot_id: str | None = None


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


class ChatActivityToolOutput(ToolOutput[ChatActivityResponse]):
    pass
