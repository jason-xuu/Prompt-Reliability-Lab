"""
Configuration module for Prompt Reliability Lab.

Loads settings from environment variables (.env file) and provides
typed access to all configuration values used across the evaluation harness.
"""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = PROJECT_ROOT / "prompts"
TEMPLATES_DIR = PROMPTS_DIR / "templates"
REPORTS_DIR = PROJECT_ROOT / "reports"

# Ensure output dirs exist
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class LlmConfig:
    """Configuration for the LLM provider (Gemini or OpenAI)."""

    provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "gemini"))
    api_key: str = field(repr=False, default_factory=lambda: os.getenv("GEMINI_API_KEY", "") or os.getenv("OPENAI_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gemini-2.0-flash"))
    temperature: float = field(
        default_factory=lambda: float(os.getenv("LLM_TEMPERATURE", "0.2"))
    )
    max_tokens: int = 2048

    def validate(self) -> None:
        """Raise if the configuration is unusable."""
        if self.provider == "ollama":
            return  # No API key needed for local Ollama
        if not self.api_key:
            raise ValueError(
                "No API key set. Add GEMINI_API_KEY or OPENAI_API_KEY to your .env file."
            )


@dataclass(frozen=True)
class EvalConfig:
    """Configuration for the evaluation harness."""

    consistency_runs: int = field(
        default_factory=lambda: int(os.getenv("CONSISTENCY_RUNS", "3"))
    )
    max_concurrent: int = field(
        default_factory=lambda: int(os.getenv("MAX_CONCURRENT_REQUESTS", "5"))
    )
    corpus_path: Path = PROMPTS_DIR / "corpus.csv"
    gold_path: Path = PROMPTS_DIR / "gold_expectations.json"


def get_llm_config() -> LlmConfig:
    """Return a validated LLM configuration."""
    cfg = LlmConfig()
    cfg.validate()
    return cfg


def get_eval_config() -> EvalConfig:
    """Return the evaluation configuration."""
    return EvalConfig()
