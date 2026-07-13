"""AgentService — business logic for provider management, session persistence, and agent run.

Used by cli/repl.py. Returns structured dicts, no ANSI/HTML formatting.

NOTE: This is a Python app service, not a Web DTO layer. Methods like
create_provider() return live provider instances, and load_session() returns
Session objects. FastAPI routers should convert these to JSON summaries
themselves.

Session ownership: AgentService mutates the session passed to run_stream()
directly. Callers that need rollback (e.g. REPL timeout) must pass a copy.
"""

from __future__ import annotations

import os
from typing import Any, Iterator


def _ok(**kwargs: Any) -> dict[str, Any]:
    return {"ok": True, **kwargs}


def _err(error: str) -> dict[str, Any]:
    return {"ok": False, "error": error}


class AgentService:
    """Stateless service: each method takes what it needs."""

    # --- Provider management ---

    @staticmethod
    def create_provider(config: dict, provider_name: str) -> dict[str, Any]:
        """Create an LLM provider instance from config.

        Returns _ok(provider=<LLMProvider>) on success.
        """
        from providers.factory import ProviderFactory

        providers = config.get("llm", {}).get("providers") or {}
        provider_config = providers.get(provider_name)
        if not provider_config:
            available = sorted(providers.keys())
            return _err(
                f"Unknown provider '{provider_name}'. "
                f"Available: {', '.join(available) or '(none)'}"
            )

        agent_config = config.get("agent", {})
        try:
            provider = ProviderFactory.create(provider_config, agent_config)
        except Exception as e:
            return _err(f"Failed to create provider: {e}")

        return _ok(provider=provider)

    @staticmethod
    def list_providers(config: dict) -> dict[str, Any]:
        """List all configured providers with availability status.

        Returns _ok(providers=[{name, type, model, api_key_env, configured}, ...]).
        """
        providers_cfg = config.get("llm", {}).get("providers") or {}
        default_provider = config.get("llm", {}).get("default_provider", "")

        providers = []
        for name, cfg in providers_cfg.items():
            api_key_env = cfg.get("api_key_env", "")
            providers.append({
                "name": name,
                "type": cfg.get("type", "unknown"),
                "model": cfg.get("model", "?"),
                "api_key_env": api_key_env,
                "configured": bool(os.getenv(api_key_env)) if api_key_env else False,
                "is_default": name == default_provider,
            })

        return _ok(providers=providers)

    # --- Session management ---

    @staticmethod
    def list_sessions(save_dir: str) -> dict[str, Any]:
        """List all saved sessions with metadata."""
        from core.session import Session

        summaries = Session.list_session_summaries(save_dir)
        return _ok(sessions=summaries)

    @staticmethod
    def save_session(session, save_dir: str, name: str = "") -> dict[str, Any]:
        """Save a session to disk.

        Returns _ok(path=..., session_id=...).
        """
        from core.session import Session

        os.makedirs(save_dir, exist_ok=True)
        if name:
            session.name = name
            session.name_source = "manual"

        normalized = session.session_id
        if normalized.endswith(".json"):
            normalized = normalized[:-5]
        save_path = os.path.join(save_dir, f"{normalized}.json")

        session.save_to_file(save_path)
        return _ok(path=save_path, session_id=session.session_id)

    @staticmethod
    def load_session(query: str, save_dir: str) -> dict[str, Any]:
        """Resolve a session by fuzzy match (exact → prefix → name) and load from disk.

        Only matches against session_id/name from list_session_summaries —
        does NOT accept arbitrary file paths (prevents path traversal).

        Returns _ok(session=<Session>) on success.
        """
        from core.session import Session

        query = query.strip()
        if query.endswith(".json"):
            query = query[:-5]

        summaries = Session.list_session_summaries(save_dir)
        if not summaries:
            return _err("No saved sessions found")

        # Exact match
        session_id = None
        for s in summaries:
            if s["session_id"] == query:
                session_id = s["session_id"]
                break

        # Prefix match
        if session_id is None:
            matches = [s for s in summaries if s["session_id"].startswith(query)]
            if len(matches) == 1:
                session_id = matches[0]["session_id"]
            elif len(matches) > 1:
                return _err(f"Ambiguous session ID prefix '{query}', matches {len(matches)} sessions")

        # Name match (case-insensitive)
        if session_id is None:
            name_matches = [s for s in summaries if query.lower() in s["name"].lower()]
            if len(name_matches) == 1:
                session_id = name_matches[0]["session_id"]
            elif len(name_matches) > 1:
                return _err(f"Ambiguous name '{query}', matches {len(name_matches)} sessions")

        if session_id is None:
            return _err(f"Session not found: {query}")

        load_path = os.path.join(save_dir, f"{session_id}.json")
        try:
            session = Session.load_from_file(load_path)
        except Exception as e:
            return _err(f"Failed to load session: {e}")

        return _ok(session=session)

    @staticmethod
    def rename_session(query: str, save_dir: str, name: str) -> dict[str, Any]:
        result = AgentService.load_session(query, save_dir)
        if not result["ok"]:
            return result
        session = result["session"]
        session.name = name.strip()
        session.name_source = "manual"
        return AgentService.save_session(session, save_dir)

    @staticmethod
    def delete_session(query: str, save_dir: str) -> dict[str, Any]:
        result = AgentService.load_session(query, save_dir)
        if not result["ok"]:
            return result
        session = result["session"]
        path = os.path.join(save_dir, f"{session.session_id}.json")
        try:
            os.remove(path)
        except OSError as exc:
            return _err(f"Failed to delete session: {exc}")
        return _ok(session_id=session.session_id)

    # --- Agent run ---

    @staticmethod
    def run_stream(
        session,
        user_input: str,
        provider,
        skills_prompt: str | None = None,
        memory_prompt: str | None = None,
        mcp_prompt: str | None = None,
        request_prompt: str | None = None,
        trace_writer=None,
        tools_schema: list[dict] | None = None,
        allowed_tool_names: set[str] | frozenset[str] | None = None,
    ) -> Iterator[dict]:
        """Create an AgentLoop and return its event stream iterator.

        The caller is responsible for threading, timeouts, and UI rendering.
        The session is mutated directly — callers needing rollback must pass a copy.

        Yields events: assistant_delta, tool_start, tool_end, specialist_event, assistant_done.
        """
        from core.agent_loop import AgentLoop

        agent = AgentLoop(
            provider,
            session,
            skills_prompt=skills_prompt,
            memory_prompt=memory_prompt,
            mcp_prompt=mcp_prompt,
            request_prompt=request_prompt,
            trace_writer=trace_writer,
            tools_schema=tools_schema,
            allowed_tool_names=allowed_tool_names,
        )
        return agent.run_stream(user_input)
