from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency guard
    load_dotenv = None


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
SAMPLE_DOCS_DIR = DATA_DIR / "sample_docs"
PROMPTS_DIR = ROOT_DIR / "prompts"

if load_dotenv:
    load_dotenv(ROOT_DIR / ".env")


DATABASE_PATH = Path(os.getenv("DATABASE_PATH", DATA_DIR / "ai_reliability_studio.db"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL_A = os.getenv("OPENAI_MODEL_A", "gpt-4o-mini")
OPENAI_MODEL_B = os.getenv("OPENAI_MODEL_B", "gpt-4.1-mini")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL_A = os.getenv("GEMINI_MODEL_A", "gemini-3.5-flash")
GEMINI_MODEL_B = os.getenv("GEMINI_MODEL_B", "gemini-3.5-flash-lite")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL_A = os.getenv("ANTHROPIC_MODEL_A", "claude-sonnet-5")
ANTHROPIC_MODEL_B = os.getenv("ANTHROPIC_MODEL_B", "claude-haiku-4-5")

DEFAULT_TOP_K = int(os.getenv("DEFAULT_TOP_K", "3"))
DEFAULT_SIMILARITY_THRESHOLD = float(os.getenv("DEFAULT_SIMILARITY_THRESHOLD", "0.05"))
LATENCY_THRESHOLD_MS = int(os.getenv("LATENCY_THRESHOLD_MS", "3500"))
COST_THRESHOLD_USD = float(os.getenv("COST_THRESHOLD_USD", "0.03"))

TOKEN_PRICING_PER_1K = {
    "mock-model": {"input": 0.0, "output": 0.0},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4.1-mini": {"input": 0.0004, "output": 0.0016},
    "gemini-3.5-flash": {"input": 0.0015, "output": 0.009},
    "gemini-3.5-flash-lite": {"input": 0.00025, "output": 0.0015},
    "claude-sonnet-5": {"input": 0.003, "output": 0.015},
    "claude-haiku-4-5": {"input": 0.001, "output": 0.005},
}

PROVIDER_MODELS = {
    "openai": [OPENAI_MODEL_A, OPENAI_MODEL_B],
    "gemini": [GEMINI_MODEL_A, GEMINI_MODEL_B],
    "anthropic": [ANTHROPIC_MODEL_A, ANTHROPIC_MODEL_B],
}

PROVIDER_API_KEYS = {
    "openai": OPENAI_API_KEY,
    "gemini": GEMINI_API_KEY,
    "anthropic": ANTHROPIC_API_KEY,
}

ESCALATION_KEYWORDS = [
    "loan approval",
    "loan rejection",
    "refund dispute",
    "fraud",
    "identity mismatch",
    "compliance",
    "legal",
    "final eligibility",
    "manual approval",
    "chargeback",
]


def available_models(api_key: str | None = None, provider: str = "openai") -> list[str]:
    models = ["mock-model"]
    provider = provider.lower()
    if api_key or PROVIDER_API_KEYS.get(provider):
        models.extend(PROVIDER_MODELS.get(provider, []))
    return list(dict.fromkeys([m for m in models if m]))


def api_key_for_provider(provider: str) -> str:
    return PROVIDER_API_KEYS.get(provider.lower(), "")


def provider_for_model(model_name: str) -> str:
    if model_name.startswith("gemini-"):
        return "gemini"
    if model_name.startswith("claude-"):
        return "anthropic"
    return "openai"


def estimate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    pricing = TOKEN_PRICING_PER_1K.get(model_name)
    if model_name == "mock-model" or not pricing:
        return 0.0
    return (
        (input_tokens / 1000.0) * pricing["input"]
        + (output_tokens / 1000.0) * pricing["output"]
    )


def approx_tokens(text: str) -> int:
    words = len((text or "").split())
    return max(1, int(words * 1.3))
