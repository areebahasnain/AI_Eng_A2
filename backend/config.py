"""Settings, read from environment variables (and the project's ``.env`` file).

The OpenRouter API key lives only here, on the backend.  ``public_dict`` is the
only thing sent to the browser and never contains the key.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# suite -> (min scramble length, max scramble length)
SUITES: dict[str, tuple[int, int]] = {
    "warmup": (3, 3),
    "primary": (3, 3),
    "extension": (3, 3),
}


@dataclass(frozen=True)
class ModelSpec:
    key: str
    name: str
    model_id: str
    category: str  # "decision" (System-1) or "llm" (frontier)
    api: str  # "decisions" or "chat"
    badge: str
    color: str


def _ledger_path_from_env() -> Path:
    configured = Path(os.environ.get("LEDGER_PATH", str(ROOT / "data" / "usage.sqlite3")))
    return (ROOT / configured).resolve() if not configured.is_absolute() else configured.resolve()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(_env(name) or default)
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    api_key: str = ""
    base_url: str = "https://openrouter.ai/api"
    app_url: str = "http://localhost:8000"
    student_name: str = ""
    student_roll_no: str = ""
    max_moves: int = 20
    time_limit_s: float = 300.0
    request_timeout_s: float = 60.0
    max_retries: int = 0
    retry_backoff_s: float = 0.5
    recent_window: int = 6
    max_consecutive_failures: int = 3
    llm_max_tokens: int = 2048
    llm_structured: bool = True
    llm_temperature: float | None = None
    llm_reasoning_effort: str = ""
    mock: bool = True
    mock_speed: float = 1.0
    provider: str = "mock"  # mock | openrouter | ollama
    allow_live_api: bool = False
    ledger_path: Path = field(default_factory=_ledger_path_from_env)
    ollama_base_url: str = "http://localhost:11434"
    ollama_request_timeout_s: float = 300.0  # separate from restricted hosted API timeout
    ollama_time_limit_s: float = 1200.0
    ollama_max_tokens: int = 128
    ollama_disable_thinking: bool = True
    ollama_stop_on_repeat_loop: bool = False  # local diagnostic only; strict benchmarks use 20 turns
    ollama_sticker_hints: bool = False  # heuristic can favor a move that is NOT closer to solved
    ollama_rotate_actions: bool = True  # deterministic, identical ordering for identical observation
    ollama_prompt_variant: str = "neutral"  # use legacy only for A/B diagnosis
    models: list[ModelSpec] = field(default_factory=list)

    def model_map(self) -> dict[str, ModelSpec]:
        return {m.key: m for m in self.models}

    def public_dict(self) -> dict:
        """Everything the browser may see.  Deliberately excludes the API key."""
        return {
            "student_name": self.student_name,
            "student_roll_no": self.student_roll_no,
            "mock": self.mock,
            "provider": self.provider,
            "policy": {"distance": 3, "max_calls_total": 65, "decision_calls_per_model": 20, "opus_calls": 5},
            "api_key_set": bool(self.api_key),
            "allow_live_api": self.allow_live_api,
            "limits": {
                "max_moves": self.max_moves,
                "time_limit_s": self.time_limit_s,
                "request_timeout_s": self.request_timeout_s,
                "max_retries": self.max_retries,
                "recent_window": self.recent_window,
            },
            "suites": {k: {"min": lo, "max": hi} for k, (lo, hi) in SUITES.items()},
            "models": [
                {
                    "key": m.key,
                    "name": m.name,
                    "model_id": m.model_id,
                    "category": m.category,
                    "api": m.api,
                    "badge": m.badge,
                    "color": m.color,
                }
                for m in self.models
            ],
        }


def ollama_models() -> list[ModelSpec]:
    """Genuine local substitutes, never mislabelled as the hosted four models."""
    return [
        ModelSpec("clef_local", "Clef Flash (local)", _env("OLLAMA_MODEL_CLEF", "clef-flash"),
                  "decision", "systemone", "LOCAL DECISION", "#f38020"),
        ModelSpec("qwen_local", "Qwen (local)", _env("OLLAMA_MODEL_QWEN", "qwen3.5"),
                  "llm", "ollama_chat", "LOCAL LLM", "#10a37f"),
        ModelSpec("llama_local", "Llama 3.2 (local)", _env("OLLAMA_MODEL_LLAMA", "llama3.2:3b"),
                  "llm", "ollama_chat", "LOCAL LLM", "#a855f7"),
        ModelSpec("gemma_local", "Gemma (local)", _env("OLLAMA_MODEL_GEMMA", "gemma3"),
                  "llm", "ollama_chat", "LOCAL LLM", "#d97757"),
    ]


def load_settings() -> Settings:
    """Read settings fresh from the environment (so tests/.env edits are honoured)."""
    api_key = _env("OPENROUTER_API_KEY")
    temp_raw = _env("LLM_TEMPERATURE")
    try:
        temperature = float(temp_raw) if temp_raw else None
    except ValueError:
        temperature = None

    models = [
        # Display order follows the assignment's reference screenshot: Opus first.
        ModelSpec(
            "opus",
            "Claude Opus 5.5",
            _env("MODEL_ID_OPUS", "anthropic/claude-opus-5.5"),
            "llm",
            "chat",
            "LLM",
            "#d97757",
        ),
        ModelSpec(
            "jev",
            "Jev 1.13",
            _env("MODEL_ID_JEV", "typesafe/jev-1.13"),
            "decision",
            "decisions",
            "DECISION MODEL",
            "#a855f7",
        ),
        ModelSpec(
            "luna",
            "GPT-6 Luna Decisions",
            _env("MODEL_ID_LUNA", "openai/gpt-6-luna-decisions"),
            "decision",
            "decisions",
            "DECISION MODEL",
            "#10a37f",
        ),
        ModelSpec(
            "clef",
            "Cloudflare Clef",
            _env("MODEL_ID_CLEF", "cloudflare/clef"),
            "decision",
            "decisions",
            "DECISION MODEL",
            "#f38020",
        ),
    ]
    return Settings(
        api_key=api_key,
        base_url=_env("OPENROUTER_BASE_URL", "https://openrouter.ai/api").rstrip("/"),
        app_url=_env("APP_URL", "http://localhost:8000"),
        student_name=_env("STUDENT_NAME"),
        student_roll_no=_env("STUDENT_ROLL_NO"),
        max_moves=min(20, max(1, _int("MAX_MOVES", 20))),
        time_limit_s=max(0.01, _float("TIME_LIMIT_S", 300.0)),
        request_timeout_s=max(1.0, _float("REQUEST_TIMEOUT_S", 60.0)),
        max_retries=0,  # repeated requests would defeat caching / budget; zero always
        retry_backoff_s=max(0.0, _float("RETRY_BACKOFF_S", 0.5)),
        recent_window=max(0, _int("RECENT_MOVES_WINDOW", 6)),
        max_consecutive_failures=max(1, _int("MAX_CONSECUTIVE_FAILURES", 3)),
        llm_max_tokens=max(64, _int("LLM_MAX_TOKENS", 2048)),
        llm_structured=_bool("LLM_STRUCTURED_OUTPUT", True),
        llm_temperature=temperature,
        llm_reasoning_effort=_env("LLM_REASONING_EFFORT").lower(),
        mock=_bool("MOCK", True),  # safe-by-default: setting a key NEVER starts paid calls
        mock_speed=max(0.01, _float("MOCK_SPEED", 1.0)),
        provider="mock" if _bool("MOCK", True) else "openrouter",
        ledger_path=_ledger_path_from_env(),
        ollama_base_url=_env("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
        ollama_request_timeout_s=max(5.0, _float("OLLAMA_REQUEST_TIMEOUT_S", 300.0)),
        ollama_time_limit_s=max(10.0, _float("OLLAMA_TIME_LIMIT_S", 1200.0)),
        ollama_max_tokens=max(16, _int("OLLAMA_MAX_TOKENS", 128)),
        ollama_disable_thinking=_bool("OLLAMA_DISABLE_THINKING", True),
        ollama_stop_on_repeat_loop=_bool("OLLAMA_STOP_ON_REPEAT_LOOP", False),
        ollama_sticker_hints=_bool("OLLAMA_STICKER_HINTS", False),
        ollama_rotate_actions=_bool("OLLAMA_ROTATE_ACTIONS", True),
        ollama_prompt_variant="legacy" if _env("OLLAMA_PROMPT_VARIANT", "neutral").lower() == "legacy" else "neutral",
        allow_live_api=_bool("ALLOW_LIVE_API", False),
        models=models,
    )
