"""
Unified LLM interface over Google Gemini and Groq.
Agents import only this module — never the underlying SDKs directly.
"""
from __future__ import annotations

import json
import time
from enum import StrEnum
from typing import Any

from app.config import Settings
from app.tracing import traced_generation
from pydantic import BaseModel

_RETRY_ATTEMPTS = 4
_RETRY_BASE_DELAY = 20.0  # seconds; doubles each attempt


class Provider(StrEnum):
    GEMINI = "gemini"
    GROQ = "groq"


def infer_provider(model: str) -> Provider:
    """Groq model IDs are namespaced ("openai/gpt-oss-20b"); Gemini's are not.

    Letting agents derive the provider from the configured model name (rather than
    hardcoding it) means swapping SCHEMA_LINKER_MODEL/SQL_GENERATOR_MODEL/etc. via
    env vars actually switches providers too, instead of silently sending a Groq
    model ID to the Gemini SDK (or vice versa).
    """
    return Provider.GROQ if "/" in model else Provider.GEMINI


def _is_transient_error(exc: Exception) -> bool:
    """Rate limits (429) and provider-side overload (503) are both worth retrying —
    the caller did nothing wrong, the request just needs to be resent."""
    status_code = getattr(exc, "status_code", None)
    if status_code in (429, 503):
        return True
    text = str(exc)
    return (
        "429" in text
        or "RESOURCE_EXHAUSTED" in text
        or "rate_limit" in text.lower()
        or "503" in text
        or "UNAVAILABLE" in text
    )


def _call_with_retry(provider_label: str, fn):
    """Retry `fn()` with exponential backoff on transient errors, for any provider."""
    delay = _RETRY_BASE_DELAY
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            return fn()
        except Exception as exc:
            if _is_transient_error(exc) and attempt < _RETRY_ATTEMPTS - 1:
                print(
                    f"  [{provider_label}] rate-limited, retrying in {delay:.0f}s… "
                    f"(attempt {attempt + 1}/{_RETRY_ATTEMPTS - 1})"
                )
                time.sleep(delay)
                delay *= 2
            else:
                raise


class LLMResponse(BaseModel):
    text: str
    parsed: Any | None = None          # Populated when response_schema is given
    model: str
    provider: Provider
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float


def _make_groq_strict_schema(pydantic_cls: type[BaseModel]) -> dict:
    """
    Convert a Pydantic model to a Groq-compatible strict JSON schema.
    Strict mode requires:
      - additionalProperties=false on every object
      - ALL properties listed in required (even those with defaults)
    """
    schema = pydantic_cls.model_json_schema()
    _patch_object(schema)
    for defn in schema.get("$defs", {}).values():
        _patch_object(defn)
    return schema


def _patch_object(obj: dict) -> None:
    """Enforce Groq strict-mode constraints on a single object schema."""
    if obj.get("type") != "object" and "properties" not in obj:
        return
    obj["additionalProperties"] = False
    if "properties" in obj:
        obj["required"] = list(obj["properties"].keys())


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._gemini: Any | None = None   # google.genai.Client
        self._groq: Any | None = None     # groq.Groq

    def _get_gemini(self) -> Any:
        if self._gemini is None:
            from google import genai
            self._gemini = genai.Client(api_key=self._settings.gemini_api_key)
        return self._gemini

    def _get_groq(self) -> Any:
        if self._groq is None:
            from groq import Groq
            self._groq = Groq(api_key=self._settings.groq_api_key)
        return self._groq

    def generate(
        self,
        *,
        provider: Provider,
        model: str,
        system: str,
        user: str,
        temperature: float = 0.0,
        response_schema: type[BaseModel] | None = None,
        agent_name: str = "llm_call",
    ) -> LLMResponse:
        t0 = time.perf_counter()
        with traced_generation(agent_name, model, system, user) as gen:
            try:
                if provider == Provider.GEMINI:
                    result = self._call_gemini(model, system, user, temperature, response_schema)
                else:
                    result = self._call_groq(model, system, user, temperature, response_schema)
            except Exception as exc:
                if gen is not None:
                    gen.update(level="ERROR", status_message=str(exc))
                raise
            result.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            if gen is not None:
                gen.update(
                    output=result.text,
                    usage_details={
                        "input": result.input_tokens or 0,
                        "output": result.output_tokens or 0,
                    },
                )
            return result

    # ------------------------------------------------------------------
    # Gemini path
    # ------------------------------------------------------------------
    def _call_gemini(
        self,
        model: str,
        system: str,
        user: str,
        temperature: float,
        response_schema: type[BaseModel] | None,
    ) -> LLMResponse:
        from google.genai import types

        config_kwargs: dict[str, Any] = {
            "system_instruction": system,
            "temperature": temperature,
        }
        if response_schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = response_schema

        client = self._get_gemini()
        resp = _call_with_retry(
            "Gemini",
            lambda: client.models.generate_content(
                model=model,
                contents=user,
                config=types.GenerateContentConfig(**config_kwargs),
            ),
        )

        usage = resp.usage_metadata
        parsed = resp.parsed if response_schema is not None else None
        return LLMResponse(
            text=resp.text or "",
            parsed=parsed,
            model=model,
            provider=Provider.GEMINI,
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
            latency_ms=0.0,
        )

    # ------------------------------------------------------------------
    # Groq path
    # ------------------------------------------------------------------
    def _call_groq(
        self,
        model: str,
        system: str,
        user: str,
        temperature: float,
        response_schema: type[BaseModel] | None,
    ) -> LLMResponse:
        client = self._get_groq()
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        if response_schema is not None:
            strict_schema = _make_groq_strict_schema(response_schema)
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_schema.__name__,
                    "strict": True,
                    "schema": strict_schema,
                },
            }

        resp = _call_with_retry("Groq", lambda: client.chat.completions.create(**kwargs))
        text = resp.choices[0].message.content or ""
        parsed = None
        if response_schema is not None:
            parsed = response_schema.model_validate(json.loads(text))

        usage = resp.usage
        return LLMResponse(
            text=text,
            parsed=parsed,
            model=model,
            provider=Provider.GROQ,
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            latency_ms=0.0,
        )
