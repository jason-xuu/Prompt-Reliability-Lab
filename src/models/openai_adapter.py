"""
OpenAI LLM adapter.

Wraps the OpenAI chat-completion API with retry logic, structured JSON output
parsing, and latency tracking.  Exposes a single ``generate()`` method consumed
by the runner.
"""

from __future__ import annotations

import json
import time
import logging
from typing import Any

from openai import OpenAI, APIError, RateLimitError, APITimeoutError

from src.config import LlmConfig

logger = logging.getLogger(__name__)


class OpenAIAdapter:
    """Thin wrapper around the OpenAI chat-completion endpoint."""

    def __init__(self, config: LlmConfig) -> None:
        config.validate()
        self._client = OpenAI(api_key=config.api_key)
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
        Send a prompt to the model and return parsed results.

        Parameters
        ----------
        system_prompt : str
            The system-level instruction (prompt template).
        user_prompt : str
            The user's natural-language geometry request.
        retries : int
            Number of retry attempts on transient failures.
        expect_json : bool
            If True, attempt to parse the assistant's response as JSON.

        Returns
        -------
        dict with keys:
            - ``raw_response``  : str   – the full assistant message
            - ``parsed``        : dict | None – parsed JSON (if expect_json)
            - ``latency_ms``    : float – round-trip time in milliseconds
            - ``model``         : str   – model used
            - ``error``         : str | None – error message if any
        """
        last_error: str | None = None

        for attempt in range(1, retries + 1):
            try:
                return self._call(system_prompt, user_prompt, expect_json)
            except (RateLimitError, APITimeoutError) as exc:
                wait = 2 ** attempt
                logger.warning(
                    "Transient error (attempt %d/%d): %s — retrying in %ds",
                    attempt, retries, exc, wait,
                )
                last_error = str(exc)
                time.sleep(wait)
            except APIError as exc:
                logger.error("Non-retryable API error: %s", exc)
                return {
                    "raw_response": "",
                    "parsed": None,
                    "latency_ms": 0.0,
                    "model": self._model,
                    "error": str(exc),
                }

        return {
            "raw_response": "",
            "parsed": None,
            "latency_ms": 0.0,
            "model": self._model,
            "error": f"Exhausted {retries} retries. Last error: {last_error}",
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
                error = f"JSON parse error: {exc}"
                logger.warning("Failed to parse JSON response: %s", raw[:200])

        return {
            "raw_response": raw,
            "parsed": parsed,
            "latency_ms": round(elapsed_ms, 1),
            "model": self._model,
            "error": error,
        }
