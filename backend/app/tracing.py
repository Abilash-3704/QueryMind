"""
Langfuse observability (spec §9).

Every agent's LLM call funnels through LLMClient.generate() (llm_client.py), which is
instrumented once here via traced_generation() — agents never touch Langfuse directly.
traced_session() wraps a full pipeline invocation (one call site: routes/query.py, plus
the eval harness) in a root span; because the SDK is OTel-based, every generation created
while that span is active automatically nests under it as a child observation — no need
to thread a "parent span" object through every agent function signature.

Graceful degradation: if LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY aren't set, every helper
below no-ops silently. Callers (llm_client.py, routes/query.py) never need their own
enabled/disabled checks.
"""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
from typing import Any

from app.config import get_settings
from langfuse import Langfuse, propagate_attributes

_client: Langfuse | None = None
_DISABLED = object()  # sentinel distinguishing "not yet checked" from "checked, no keys"


def get_langfuse() -> Langfuse | None:
    """Configured Langfuse client, or None if keys aren't set. Callers must handle None."""
    global _client
    if _client is _DISABLED:
        return None
    if _client is None:
        settings = get_settings()
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            _client = _DISABLED
            return None
        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    return _client


@contextmanager
def traced_session(session_id: str | None, name: str, metadata: dict[str, Any] | None = None):
    """Wrap a full pipeline invocation in one root span. session_id propagates to every
    nested generation created while this context is active. No-ops if unconfigured."""
    client = get_langfuse()
    if client is None:
        yield
        return
    with client.start_as_current_observation(as_type="span", name=name, metadata=metadata):
        with propagate_attributes(session_id=session_id) if session_id else nullcontext():
            yield


@contextmanager
def traced_generation(agent_name: str, model: str, system: str, user: str):
    """Wrap one LLM call as a Langfuse generation observation. Yields the generation
    handle (call .update(...) on it) or None if unconfigured — callers must check."""
    client = get_langfuse()
    if client is None:
        yield None
        return
    with client.start_as_current_observation(
        as_type="generation",
        name=agent_name,
        model=model,
        input={"system": system, "user": user},
    ) as gen:
        yield gen


def flush_langfuse() -> None:
    """Flush buffered spans before a short-lived process (eval scripts) exits.
    No-op if unconfigured."""
    client = get_langfuse()
    if client is not None:
        client.flush()
