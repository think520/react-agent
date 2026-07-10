"""Pydantic DTOs exposed by the Web API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class ChatRunRequest(BaseModel):
    message: str = Field(..., min_length=1)
    chat_session_id: str | None = None
    provider: str | None = None
    save: bool = True


class ChatSessionUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatSessionSummary(BaseModel):
    chat_session_id: str
    name: str
    created_at: str
    last_active: str
    message_count: int


class ChatSessionDetail(ChatSessionSummary):
    messages: list[ChatMessage]


class SourceRef(BaseModel):
    source_type: Literal["local", "web"]
    source_id: str
    title: str
    url: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    heading: str | None = None
    page: int | None = None
    slide: int | None = None


class Attribution(BaseModel):
    kind: Literal["local", "local_extension", "web", "ai", "unverified"]
    sources: list[SourceRef] = Field(default_factory=list)

