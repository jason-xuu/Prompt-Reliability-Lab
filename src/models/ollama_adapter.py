"""
Ollama LLM adapter.

Uses the OpenAI-compatible API that Ollama exposes at localhost:11434.
No rate limits, no API key, no cost — runs 100% locally.
"""

from __future__ import annotations

import json
import time
import logging
from typing import Any

from openai import OpenAI

from src.config import LlmConfig

logger = logging.getLogger(__name__)

# Ollama serves an OpenAI-compatible endpoint
OLLAMA_BASE_URL = "http://localhost:11434/v1"


class OllamaAdapter:
    """Thin wrapper around Ollama's OpenAI-compatible API."""

    def __init__(self, config: LlmConfig) -> None:
        self._client = OpenAI(
            base_url=OLLAMA_BASE_URL,
            api_key="ollama",  # Ollama doesn't need a real key
        )
        self._model = config.model
        self._temperature = config.temperature
        self._max_tokens = config.max_tokens

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        retries: int = 3,
        expect_json: bool = True,
    ) -> dict[str, Any]:
        """
        Send a prompt to the local Ollama model and return parsed results.

        Returns
        -------
        dict with keys:
            - ``raw_response``  : str   – the full assistant message
            - ``parsed``        : dict | None – parsed JSON (if expect_json)
            - ``latency_ms``    : float – round-trip time in milliseconds
            - ``model``         : str   – model used
            - ``error``         : str | None – error message if any
        """
        last_error = None

        for attempt in range(1, retries + 1):
            try:
                return self._call(system_prompt, user_prompt, expect_json)
            except Exception as exc:
                wait = 2 ** attempt
                logger.warning(
                    "Ollama error (attempt %d/%d): %s — retrying in %ds",
                    attempt, retries, exc, wait,
                )
                last_error = str(exc)
                time.sleep(wait)

        return {
            "raw_response": "",
            "parsed": None,
            "latency_ms": 0.0,
            "model": self._model,
            "error": "Exhausted %d retries. Last error: %s" % (retries, last_error),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _call(
        self, system_prompt: str, user_prompt: str, expect_json: bool
    ) -> dict[str, Any]:
        start = time.perf_counter()

        kwargs: dict[str, Any] = {
            "model": self._model,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if expect_json:
            kwargs["response_format"] = {"type": "json_object"}

        response = self._client.chat.completions.create(**kwargs)
        elapsed_ms = (time.perf_counter() - start) * 1000

        raw = response.choices[0].message.content or ""
        parsed = None
        error = None

        if expect_json:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                error = "JSON parse error: %s" % exc
                logger.warning("Failed to parse JSON response: %s", raw[:200])

        return {
            "raw_response": raw,
            "parsed": parsed,
            "latency_ms": round(elapsed_ms, 1),
            "model": self._model,
            "error": error,
        }
