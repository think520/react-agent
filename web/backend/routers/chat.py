"""Chat run and session endpoints."""

from __future__ import annotations

import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from core.session import Session
from service.agent_service import AgentService
from core.skills import find_skill_by_name
from web.backend.capabilities import WEB_SKILL_NAMES
from service.kb_service import KBService
from tools import get_tools_schema
from web.backend.deps import (
    get_config,
    get_default_provider_name,
    get_runtime_context,
    get_session_save_dir,
)
from web.backend.errors import APIError
from web.backend.events import to_web_events
from web.backend.schemas import ChatRunRequest, ChatSessionUpdateRequest
from web.backend.sse import encode_sse

router = APIRouter()
logger = logging.getLogger(__name__)

_UNTITLED_NAMES = {"", "未命名会话", "Untitled", "Untitled session"}

_WEB_TOOL_NAMES = frozenset({
    "rag_search",
    "graph_query",
    "knowledge_status",
    "question_generate",
    "quiz_start",
    "quiz_submit",
    "learning_path",
    "learning_progress",
    "learning_review",
    "memory_save",
    "memory_recall",
    "memory_daily_save",
    "memory_daily_read",
    "memory_promote",
})
_MEMORY_TOOL_NAMES = frozenset({
    "memory_save", "memory_recall", "memory_daily_save", "memory_daily_read", "memory_promote",
})


def _web_tools_schema(allowed_tool_names: frozenset[str] = _WEB_TOOL_NAMES) -> list[dict]:
    return [
        schema for schema in get_tools_schema()
        if schema.get("function", {}).get("name") in allowed_tool_names
    ]


def _load_or_create_session(chat_session_id: str | None, config: dict[str, Any]) -> Session:
    save_dir = get_session_save_dir(config)
    if chat_session_id:
        result = AgentService.load_session(chat_session_id, save_dir)
        if not result["ok"]:
            raise APIError(404, "session_not_found", result["error"])
        return result["session"]

    runtime = get_runtime_context()
    max_messages = config.get("session", {}).get("max_messages")
    return Session.new(runtime.workspace, max_messages=max_messages)


def _session_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "chat_session_id": summary.get("session_id", ""),
        "name": summary.get("name", ""),
        "name_source": summary.get("name_source", "fallback"),
        "created_at": summary.get("created_at", ""),
        "last_active": summary.get("last_active", ""),
        "message_count": summary.get("message_count", 0),
    }


def _session_detail(session: Session) -> dict[str, Any]:
    messages = []
    for message in session.messages:
        role = message.get("role")
        content = message.get("content") or ""
        if role == "user":
            messages.append({"role": "user", "content": content})
        elif role == "assistant" and not message.get("tool_calls") and content:
            item = {"role": "assistant", "content": content}
            attribution = _public_attribution(message.get("attribution"))
            if attribution:
                item["attribution"] = attribution
            messages.append(item)
    return {
        "chat_session_id": session.session_id,
        "name": session.name,
        "name_source": session.name_source,
        "created_at": session.created_at,
        "last_active": session.last_active,
        "message_count": len(messages),
        "messages": messages,
    }


def _public_attribution(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    kind = value.get("kind")
    if kind not in {"local", "local_extension", "web", "ai", "unverified"}:
        return None
    sources = []
    for source in value.get("sources") or []:
        if not isinstance(source, dict):
            continue
        source_type = source.get("source_type")
        if source_type not in {"local", "web"}:
            continue
        public = {
            key: source.get(key)
            for key in (
                "source_type", "source_id", "title", "document_id",
                "chunk_id", "heading", "page", "slide",
                "collection",
            )
            if source.get(key) is not None
        }
        if source_type == "web" and source.get("url"):
            public["url"] = source["url"]
        if public.get("source_id") and public.get("title"):
            sources.append(public)
    return {"kind": kind, "sources": sources}


def _attach_attribution(session: Session, attribution: dict[str, Any] | None) -> None:
    public = _public_attribution(attribution)
    if not public:
        return
    for message in reversed(session.messages):
        if message.get("role") == "assistant" and not message.get("tool_calls") and message.get("content"):
            message["attribution"] = public
            return


def _request_context(
    document_ids: list[str],
    workspace: str,
    learning_goal: str = "",
    web_enabled: bool = False,
) -> tuple[list[str], str | None]:
    available = {}
    if document_ids:
        result = KBService(workspace).list_documents(collection="all")
        available = {
            document["document_id"]: document
            for document in result.get("documents", [])
        }
    selected = [available[item] for item in document_ids if item in available]
    valid_ids = [item["document_id"] for item in selected]
    if not selected and not learning_goal.strip() and web_enabled:
        return [], None
    lines = [
        "<!-- bobodan:request-scope -->",
    ]
    if learning_goal.strip():
        lines.append(f"The user's current learning goal is: {learning_goal.strip()}")
    if selected:
        lines.append("The user selected these documents as the active study scope:")
        lines.extend(f"- {item['title'] or item['source']} [{item['document_id']}]" for item in selected)
        lines.append(
            "Local retrieval is automatically restricted to this scope. "
            "Ground answers and generated practice in these documents unless the user explicitly asks to widen the scope."
        )
    if not web_enabled:
        lines.append("The user has not enabled web supplementation for this request. Do not claim to have searched the web.")
    return valid_ids, "\n".join(lines)


def _slash_command_prompt(message: str, skills_dir: str) -> str | None:
    value = message.strip()
    if value.startswith("/kb search "):
        query = value[len("/kb search "):].strip()
        return (
            "<!-- [explicit_web_command] -->\n"
            "The user invoked /kb search. Use local RAG search for the query below, "
            "cite the retrieved local sources, and do not answer from general knowledge when evidence is missing.\n"
            f"Query: {query}"
        ) if query else None
    if value == "/learning today":
        return (
            "<!-- [explicit_web_command] -->\n"
            "The user invoked /learning today. Use the available learning progress and review tools "
            "to produce a concise, actionable plan for today."
        )
    if not value.startswith("/skill "):
        return None
    parts = value.split(maxsplit=2)
    if len(parts) < 2:
        return None
    if parts[1] not in WEB_SKILL_NAMES:
        return None
    skill = find_skill_by_name(skills_dir, parts[1])
    if skill is None:
        return None
    try:
        with open(skill.file_path, "r", encoding="utf-8") as handle:
            instructions = handle.read()
    except OSError:
        return None
    task = parts[2].strip() if len(parts) > 2 else "根据当前学习上下文给出下一步建议。"
    return (
        "<!-- [explicit_skill_command] -->\n"
        f'The user explicitly selected the skill "{skill.name}" for this run.\n'
        "Follow the skill instructions below, using only the tools allowed in this Web runtime.\n"
        f"User task: {task}\n\n"
        f"<selected_skill>\n{instructions}\n</selected_skill>"
    )


def _first_visible_turn(session: Session) -> tuple[str, str]:
    user_text = ""
    assistant_text = ""
    for message in session.messages:
        role = message.get("role")
        content = str(message.get("content") or "").strip()
        if role == "user" and content and not user_text:
            user_text = content
        elif role == "assistant" and content and not message.get("tool_calls") and not assistant_text:
            assistant_text = content
        if user_text and assistant_text:
            break
    return user_text, assistant_text


def _fallback_title(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:30].rstrip("，。！？,.!?；;：:") or "新对话"


def _clean_generated_title(text: str) -> str:
    title = re.sub(r"\s+", " ", text).strip()
    title = title.strip("`#*\"'“”‘’《》")
    title = re.sub(r"^(标题|会话标题)\s*[:：]\s*", "", title, flags=re.I)
    return title[:30].rstrip("，。！？,.!?；;：:")


def migrate_unnamed_sessions(save_dir: str) -> int:
    migrated = 0
    for summary in Session.list_session_summaries(save_dir):
        if summary.get("name") not in _UNTITLED_NAMES:
            continue
        result = AgentService.load_session(summary["session_id"], save_dir)
        if not result.get("ok"):
            continue
        session = result["session"]
        user_text, _ = _first_visible_turn(session)
        if not user_text:
            continue
        session.name = _fallback_title(user_text)
        session.name_source = "fallback"
        AgentService.save_session(session, save_dir)
        migrated += 1
    return migrated


@router.get("/sessions")
def list_sessions() -> dict:
    result = AgentService.list_sessions(get_session_save_dir(get_config()))
    return {"sessions": [_session_summary(item) for item in result["sessions"]]}


@router.get("/sessions/{chat_session_id}")
def get_session(chat_session_id: str) -> dict:
    result = AgentService.load_session(chat_session_id, get_session_save_dir(get_config()))
    if not result["ok"]:
        raise APIError(404, "session_not_found", result["error"])
    return _session_detail(result["session"])


@router.patch("/sessions/{chat_session_id}")
def rename_session(chat_session_id: str, request: ChatSessionUpdateRequest) -> dict:
    result = AgentService.rename_session(
        chat_session_id,
        get_session_save_dir(get_config()),
        request.name,
    )
    if not result["ok"]:
        raise APIError(404, "session_not_found", result["error"])
    return {
        "chat_session_id": result["session_id"],
        "name": request.name.strip(),
        "name_source": "manual",
    }


@router.post("/sessions/{chat_session_id}/title")
def generate_session_title(chat_session_id: str) -> dict:
    config = get_config()
    save_dir = get_session_save_dir(config)
    result = AgentService.load_session(chat_session_id, save_dir)
    if not result["ok"]:
        raise APIError(404, "session_not_found", result["error"])

    session = result["session"]
    if session.name_source == "manual":
        return {
            "chat_session_id": session.session_id,
            "name": session.name,
            "name_source": "manual",
        }

    user_text, assistant_text = _first_visible_turn(session)
    if not user_text:
        raise APIError(409, "session_has_no_user_message", "The session has no user message yet.")

    title = ""
    source = "fallback"
    if assistant_text:
        try:
            provider = get_runtime_context().create_provider(get_default_provider_name(config))
            prompt = (
                "请根据下面第一轮学习对话生成一个简洁的中文会话标题。"
                "只输出标题，不加引号、序号或解释，最多 30 个字符。\n\n"
                f"用户：{user_text[:1200]}\n\n助手：{assistant_text[:1600]}"
            )
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(provider.complete, [{"role": "user", "content": prompt}])
            try:
                response = future.result(timeout=15)
                title = _clean_generated_title(getattr(response, "content", "") or "")
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
            if title:
                source = "ai"
        except Exception as exc:
            logger.info("Session title generation fell back for %s: %s", chat_session_id, exc)

    if not title:
        title = _fallback_title(user_text)

    latest = AgentService.load_session(chat_session_id, save_dir)
    if not latest["ok"]:
        raise APIError(404, "session_not_found", latest["error"])
    session = latest["session"]
    if session.name_source != "manual":
        session.name = title
        session.name_source = source
        AgentService.save_session(session, save_dir)
    return {
        "chat_session_id": session.session_id,
        "name": session.name,
        "name_source": session.name_source,
    }


@router.delete("/sessions/{chat_session_id}")
def delete_session(chat_session_id: str) -> dict:
    result = AgentService.delete_session(chat_session_id, get_session_save_dir(get_config()))
    if not result["ok"]:
        raise APIError(404, "session_not_found", result["error"])
    return {"deleted": True, "chat_session_id": result["session_id"]}


@router.post("/runs")
def create_run(request: ChatRunRequest) -> StreamingResponse:
    config = get_config()
    runtime = get_runtime_context()
    provider_name = request.provider or get_default_provider_name(config)
    try:
        provider = runtime.create_provider(provider_name)
    except Exception as exc:
        logger.warning("Web provider creation failed for %s: %s", provider_name, exc)
        raise APIError(
            503,
            "provider_unavailable",
            "The selected AI provider is unavailable. Check its configuration and try again.",
        ) from exc

    session = _load_or_create_session(request.chat_session_id, config)
    document_ids, request_prompt = _request_context(
        request.document_ids,
        runtime.workspace,
        learning_goal=request.learning_goal,
        web_enabled=request.web_enabled,
    )
    slash_prompt = _slash_command_prompt(request.message, getattr(runtime, "skills_dir", ""))
    if slash_prompt:
        request_prompt = f"{request_prompt}\n\n{slash_prompt}" if request_prompt else slash_prompt
    session.active_document_ids = document_ids
    allowed_tool_names = _WEB_TOOL_NAMES if request.memory_enabled else _WEB_TOOL_NAMES - _MEMORY_TOOL_NAMES
    run_id = str(uuid.uuid4())

    def event_stream():
        yield encode_sse("run_started", {
            "run_id": run_id,
            "chat_session_id": session.session_id,
            "provider": provider_name,
        })
        try:
            latest_attribution = None
            if request.memory_enabled:
                runtime.refresh_memory()
            events = AgentService.run_stream(
                session=session,
                user_input=request.message,
                provider=provider,
                skills_prompt=runtime.skills_prompt,
                memory_prompt=runtime.memory_prompt if request.memory_enabled else None,
                trace_writer=runtime.create_trace(session.session_id),
                tools_schema=_web_tools_schema(allowed_tool_names),
                allowed_tool_names=allowed_tool_names,
                request_prompt=request_prompt,
            )
            termination_reason = "final_answer"
            for event in events:
                if event.get("type") == "assistant_done":
                    termination_reason = event.get("termination_reason", "final_answer")
                for web_event, payload in to_web_events(event):
                    if web_event == "citation":
                        latest_attribution = payload.get("attribution")
                    yield encode_sse(web_event, {"run_id": run_id, **payload})

            if request.save:
                _attach_attribution(session, latest_attribution)
                save_result = AgentService.save_session(session, get_session_save_dir(config))
                if not save_result["ok"]:
                    yield encode_sse("run_failed", {
                        "run_id": run_id,
                        "error": {
                            "code": "session_save_failed",
                            "message": "The conversation could not be saved.",
                        },
                    })
                    return

            yield encode_sse("run_completed", {
                "run_id": run_id,
                "chat_session_id": session.session_id,
                "termination_reason": termination_reason,
            })
        except Exception as exc:
            logger.exception("Web chat run failed: %s", exc)
            yield encode_sse("run_failed", {
                "run_id": run_id,
                "error": {
                    "code": "run_failed",
                    "message": "The AI run failed. Please try again.",
                },
            })

    return StreamingResponse(event_stream(), media_type="text/event-stream")
