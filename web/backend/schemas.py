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


class ChatReference(BaseModel):
    type: Literal["document", "session"]
    id: str = Field(..., min_length=1, max_length=160)
    title: str = Field(..., min_length=1, max_length=200)
    collection: Literal["material", "wiki"] | None = None
    wiki_type: Literal["source", "entity", "concept", "analysis", "question", "note"] | None = None


class ChatRunRequest(BaseModel):
    message: str = Field(..., min_length=1)
    chat_session_id: str | None = None
    provider: str | None = None
    save: bool = True
    document_ids: list[str] = Field(default_factory=list, max_length=200)
    preferred_document_ids: list[str] = Field(default_factory=list, max_length=200)
    learning_goal: str = Field(default="", max_length=500)
    memory_enabled: bool = True
    web_enabled: bool = False
    web_research_id: str | None = Field(default=None, max_length=64)
    references: list[ChatReference] = Field(default_factory=list, max_length=8)


class ChatSessionUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class ChatSessionProviderRequest(BaseModel):
    provider: str = Field(..., min_length=1, max_length=80)


class PracticeArtifactStartRequest(BaseModel):
    chat_session_id: str = Field(..., min_length=1, max_length=64)


class MemoryProposalResolutionRequest(BaseModel):
    chat_session_id: str = Field(..., min_length=1, max_length=64)
    warning_acknowledged: bool = False


class WikiFocusRequest(BaseModel):
    chat_session_id: str | None = None
    action: Literal["generate", "update", "repair", "migrate"] = "generate"
    scope_mode: Literal["uncovered", "smart_library", "selected_only", "course"] = "smart_library"
    document_ids: list[str] = Field(default_factory=list, max_length=200)
    wiki_document_ids: list[str] = Field(default_factory=list, max_length=20)
    course: str | None = None
    topic: str = Field(default="", max_length=500)
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


class WikiPlanRecoveryRequest(BaseModel):
    chat_session_id: str
    strategy: Literal["keep_existing", "regenerate"]
    provider: str | None = None


class WikiCheckpointRestoreRequest(BaseModel):
    chat_session_id: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    references: list[ChatReference] = Field(default_factory=list)
    personalization: list[dict[str, Any]] = Field(default_factory=list)


class ChatSessionSummary(BaseModel):
    chat_session_id: str
    name: str
    name_source: Literal["ai", "fallback", "manual"]
    created_at: str
    last_active: str
    message_count: int
    library_id: str | None = None
    provider_name: str | None = None


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
    domain: str | None = None
    accessed_at: str | None = None
    snapshot_id: str | None = None
    reader: Literal["direct", "jina"] | None = None


class Attribution(BaseModel):
    kind: Literal["local", "local_extension", "web", "ai", "unverified"]
    sources: list[SourceRef] = Field(default_factory=list)

