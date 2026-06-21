"""LLM client — wraps any OpenAI-compatible chat completions endpoint.

Configure via LLM_API_KEY / LLM_BASE_URL / LLM_MODEL in .env.
Works with OpenAI, Groq, Gemini (OpenAI-compat), Volcengine ARK, or any
provider that implements the Chat Completions API.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from config.settings import settings
from db import database as db

logger = logging.getLogger(__name__)


@dataclass
class ChatResult:
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


class LLMClient:
    """Thin wrapper over any OpenAI-compatible chat completions endpoint."""

    def __init__(self) -> None:
        self._client = None
        if settings.llm_enabled:
            try:
                from openai import OpenAI
                kwargs: dict = {"api_key": settings.llm_api_key}
                if settings.llm_base_url:
                    kwargs["base_url"] = settings.llm_base_url
                self._client = OpenAI(**kwargs)
            except Exception as exc:  # pragma: no cover
                logger.warning("LLM client init failed: %s", exc)

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def chat(self, system_prompt: str, user_prompt: str, *,
             temperature: float = 0.3, max_tokens: int = 1500,
             json_mode: bool = False, endpoint: str = "chat") -> Optional[ChatResult]:
        """Single-turn chat. Returns None if LLM is not configured/available."""
        if not self.enabled:
            logger.info("LLM not configured; skipping chat call.")
            return None

        kwargs = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            # Most OpenAI-compatible servers accept this; if a model rejects it
            # we fall back to a plain call.
            kwargs["response_format"] = {"type": "json_object"}

        try:
            resp = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            if json_mode:
                logger.warning("LLM json_mode call failed (%s); retrying plain.", exc)
                kwargs.pop("response_format", None)
                try:
                    resp = self._client.chat.completions.create(**kwargs)
                except Exception as exc2:
                    logger.error("LLM chat failed: %s", exc2)
                    return None
            else:
                logger.error("LLM chat failed: %s", exc)
                return None

        content = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        in_tok = getattr(usage, "prompt_tokens", 0) or 0
        out_tok = getattr(usage, "completion_tokens", 0) or 0

        try:
            db.log_api_usage("llm", endpoint, input_tokens=in_tok, output_tokens=out_tok)
        except Exception:
            pass  # usage logging must never break the call

        return ChatResult(content=content, input_tokens=in_tok,
                          output_tokens=out_tok, model=settings.llm_model)


# Backward-compat alias (used by tests)
ArkClient = LLMClient
