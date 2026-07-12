"""
Tracing tests — verify Langfuse instrumentation degrades gracefully when unconfigured.

No real network calls: these tests never construct a real Langfuse client, so they run
in CI without an account. Live tracing (real spans reaching the Langfuse dashboard) is
verified manually per the Phase 5 plan, not here.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.tracing as tracing_module  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_tracing_singleton():
    """tracing.py caches its Langfuse client at module scope — reset between tests
    so one test's monkeypatched settings don't leak into the next."""
    tracing_module._client = None
    yield
    tracing_module._client = None


def _settings_with_keys(public_key: str, secret_key: str) -> MagicMock:
    settings = MagicMock()
    settings.langfuse_public_key = public_key
    settings.langfuse_secret_key = secret_key
    settings.langfuse_host = "https://cloud.langfuse.com"
    return settings


def test_get_langfuse_returns_none_when_keys_blank(monkeypatch) -> None:
    monkeypatch.setattr(
        tracing_module, "get_settings", lambda: _settings_with_keys("", "")
    )
    assert tracing_module.get_langfuse() is None


def test_get_langfuse_returns_none_when_only_one_key_set(monkeypatch) -> None:
    monkeypatch.setattr(
        tracing_module, "get_settings", lambda: _settings_with_keys("pk-lf-x", "")
    )
    assert tracing_module.get_langfuse() is None


def test_traced_session_noops_when_unconfigured(monkeypatch) -> None:
    monkeypatch.setattr(
        tracing_module, "get_settings", lambda: _settings_with_keys("", "")
    )
    entered = False
    with tracing_module.traced_session("sess-1", name="test_pipeline", metadata={"k": "v"}):
        entered = True
    assert entered  # the with-block body still runs, tracing just does nothing


def test_traced_generation_noops_when_unconfigured(monkeypatch) -> None:
    monkeypatch.setattr(
        tracing_module, "get_settings", lambda: _settings_with_keys("", "")
    )
    with tracing_module.traced_generation("sql_generator", "gemini-2.5-flash-lite", "sys", "usr") as gen:
        assert gen is None  # caller must check before calling .update()


def test_flush_langfuse_noops_when_unconfigured(monkeypatch) -> None:
    monkeypatch.setattr(
        tracing_module, "get_settings", lambda: _settings_with_keys("", "")
    )
    tracing_module.flush_langfuse()  # must not raise


def test_get_langfuse_constructs_client_when_keys_present(monkeypatch) -> None:
    """Doesn't hit the network — just confirms the branch that builds a real client
    is reached and doesn't raise on construction with well-formed (fake) keys."""
    monkeypatch.setattr(
        tracing_module, "get_settings", lambda: _settings_with_keys("pk-lf-test", "sk-lf-test")
    )
    client = tracing_module.get_langfuse()
    assert client is not None
    # Second call must reuse the cached instance, not reconstruct
    assert tracing_module.get_langfuse() is client
