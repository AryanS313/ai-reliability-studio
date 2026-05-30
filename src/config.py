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

DEFAULT_TOP_K = int(os.getenv("DEFAULT_TOP_K", "3"))
DEFAULT_SIMILARITY_THRESHOLD = float(os.getenv("DEFAULT_SIMILARITY_THRESHOLD", "0.05"))
LATENCY_THRESHOLD_MS = int(os.getenv("LATENCY_THRESHOLD_MS", "3500"))
COST_THRESHOLD_USD = float(os.getenv("COST_THRESHOLD_USD", "0.03"))

TOKEN_PRICING_PER_1K = {
    "mock-model": {"input": 0.0, "output": 0.0},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4.1-mini": {"input": 0.0004, "output": 0.0016},
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


def available_models(api_key: str | None = None) -> list[str]:
    models = ["mock-model"]
    if api_key or OPENAI_API_KEY:
        models.append(OPENAI_MODEL_A)
        if OPENAI_MODEL_B and OPENAI_MODEL_B != OPENAI_MODEL_A:
            models.append(OPENAI_MODEL_B)
    return list(dict.fromkeys([m for m in models if m]))


def estimate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    pricing = TOKEN_PRICING_PER_1K.get(model_name, TOKEN_PRICING_PER_1K.get("gpt-4o-mini"))
    if model_name == "mock-model" or not pricing:
        return 0.0
    return (
        (input_tokens / 1000.0) * pricing["input"]
        + (output_tokens / 1000.0) * pricing["output"]
    )


def approx_tokens(text: str) -> int:
    words = len((text or "").split())
    return max(1, int(words * 1.3))
