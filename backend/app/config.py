"""Settings read from the project-level .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DEFAULT_MODELS = {
    "gemini": "gemini-3-flash-preview",
    "openai": "gpt-4.1",
    "ollama": "qwen3:8b",
}


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    llm_model: str
    qc_model: str
    gemini_api_key: str
    openai_api_key: str
    ollama_url: str
    tavily_api_key: str
    google_api_key: str
    llm_rpm: int
    db_path: Path


def load_settings() -> Settings:
    provider = _env("LLM_PROVIDER", "gemini").lower()
    model = _env("LLM_MODEL") or DEFAULT_MODELS.get(provider, "")
    db_path = Path(_env("DB_PATH") or "data/lessons.db")
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        rpm = int(_env("LLM_REQUESTS_PER_MINUTE", "0") or 0)
    except ValueError:
        rpm = 0
    return Settings(
        llm_provider=provider,
        llm_model=model,
        # The reviewers can use a different model from the writer, so the
        # checks are not the writer marking its own homework.
        qc_model=_env("QC_MODEL") or model,
        gemini_api_key=_env("GEMINI_API_KEY"),
        openai_api_key=_env("OPENAI_API_KEY"),
        ollama_url=_env("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
        tavily_api_key=_env("TAVILY_API_KEY"),
        google_api_key=_env("GOOGLE_API_KEY") or _env("YOUTUBE_API_KEY"),
        llm_rpm=max(rpm, 0),
        db_path=db_path,
    )


settings = load_settings()
