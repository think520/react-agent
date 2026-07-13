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
    document_ids: list[str] = Field(default_factory=list, max_length=50)
    learning_goal: str = Field(default="", max_length=500)
    memory_enabled: bool = True
    web_enabled: bool = False


class ChatSessionUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class WikiFocusRequest(BaseModel):
    chat_session_id: str | None = None
    action: Literal["generate", "update", "repair", "migrate"] = "generate"
    document_ids: list[str] = Field(default_factory=list, max_length=50)
    wiki_document_ids: list[str] = Field(default_factory=list, max_length=20)
    course: str | None = None
    instruction: str = Field(default="", max_length=1000)
    provider: str | None = None


class WikiFocusReviseRequest(BaseModel):
    chat_session_id: str
    revision: str = Field(..., min_length=1, max_length=2000)
    provider: str | None = None


class WikiFocusConfirmRequest(BaseModel):
    chat_session_id: str
    provider: str | None = None


class WikiPlanApplyRequest(BaseModel):
    chat_session_id: str


class WikiCheckpointRestoreRequest(BaseModel):
    chat_session_id: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    artifacts: list[dict[str, Any]] = Field(default_factory=list)


class ChatSessionSummary(BaseModel):
    chat_session_id: str
    name: str
    name_source: Literal["ai", "fallback", "manual"]
    created_at: str
    last_active: str
    message_count: int
    library_id: str | None = None


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
    collection: Literal["material", "wiki"] | None = None


class Attribution(BaseModel):
    kind: Literal["local", "local_extension", "web", "ai", "unverified"]
    sources: list[SourceRef] = Field(default_factory=list)

