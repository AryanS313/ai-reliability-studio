from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import TypedDict


def _load_local_environment() -> None:
    try:
        import dotenv
    except ImportError:  # pragma: no cover - optional dependency guard
        return
    dotenv.load_dotenv(Path(__file__).resolve().parents[1] / ".env")


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
SAMPLE_DOCS_DIR = DATA_DIR / "sample_docs"
PROMPTS_DIR = ROOT_DIR / "prompts"

_load_local_environment()


DATABASE_PATH = Path(os.getenv("DATABASE_PATH", DATA_DIR / "ai_reliability_studio.db"))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_PATH}")
APP_ENV = os.getenv("APP_ENV", "development").lower()
AUTH_MODE = os.getenv("AUTH_MODE", "single-user").lower()
AUTH_SESSION_MAX_AGE_SECONDS = int(os.getenv("AUTH_SESSION_MAX_AGE_SECONDS", "3600"))
AUTH_REQUIRE_ISSUED_AT = os.getenv(
    "AUTH_REQUIRE_ISSUED_AT", "true" if APP_ENV == "production" else "false"
).lower() in {"1", "true", "yes"}
SINGLE_USER_EMAIL = os.getenv("SINGLE_USER_EMAIL", "local@ai-reliability-studio.invalid")
SINGLE_USER_WORKSPACE = os.getenv("SINGLE_USER_WORKSPACE", "Local Workspace")
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
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
MAX_DATASET_ROWS = int(os.getenv("MAX_DATASET_ROWS", "10000"))
MAX_DOCUMENTS_PER_UPLOAD = int(os.getenv("MAX_DOCUMENTS_PER_UPLOAD", "50"))
MAX_EXTRACTED_CHARACTERS = int(os.getenv("MAX_EXTRACTED_CHARACTERS", "5000000"))
MAX_EXTERNAL_REQUEST_BYTES = int(os.getenv("MAX_EXTERNAL_REQUEST_BYTES", str(2 * 1024 * 1024)))
MAX_EXTERNAL_RESPONSE_BYTES = int(os.getenv("MAX_EXTERNAL_RESPONSE_BYTES", str(5 * 1024 * 1024)))
MAX_EXPORT_ROWS = int(os.getenv("MAX_EXPORT_ROWS", "100000"))
REQUIRE_MALWARE_SCAN = os.getenv("REQUIRE_MALWARE_SCAN", "true" if APP_ENV == "production" else "false").lower() in {
    "1",
    "true",
    "yes",
}
EXTERNAL_TARGET_ALLOWED_HOSTS = tuple(
    host.strip().lower() for host in os.getenv("EXTERNAL_TARGET_ALLOWED_HOSTS", "").split(",") if host.strip()
)
ALLOW_PRIVATE_EXTERNAL_TARGETS = os.getenv("ALLOW_PRIVATE_EXTERNAL_TARGETS", "false").lower() in {"1", "true", "yes"}
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "90"))
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", "30"))
PRICING_VERSION = os.getenv("PRICING_VERSION", "2026-08-20")
PRICING_EFFECTIVE_DATE = os.getenv("PRICING_EFFECTIVE_DATE", "2026-08-20")


class PricingEntry(TypedDict, total=False):
    input: float
    output: float
    source: str
    effective_date: str
    expires_on: str


TOKEN_PRICING_PER_1K: dict[str, PricingEntry] = {
    "mock-model": {"input": 0.0, "output": 0.0, "source": "synthetic", "effective_date": "2026-08-20"},
    "gpt-4o-mini": {
        "input": 0.00015,
        "output": 0.0006,
        "source": "https://developers.openai.com/api/docs/models/gpt-4o-mini",
        "effective_date": "2026-08-20",
    },
    "gpt-4.1-mini": {
        "input": 0.0004,
        "output": 0.0016,
        "source": "https://openai.com/index/gpt-4-1/",
        "effective_date": "2026-08-20",
    },
    "gemini-3.5-flash": {
        "input": 0.0015,
        "output": 0.009,
        "source": "https://ai.google.dev/gemini-api/docs/pricing",
        "effective_date": "2026-08-20",
    },
    "gemini-3.5-flash-lite": {
        "input": 0.0003,
        "output": 0.0025,
        "source": "https://ai.google.dev/gemini-api/docs/pricing",
        "effective_date": "2026-08-20",
    },
    "claude-sonnet-5": {
        "input": 0.002,
        "output": 0.01,
        "source": "https://platform.claude.com/docs/en/about-claude/pricing",
        "effective_date": "2026-08-20",
        "expires_on": "2026-08-31",
    },
    "claude-haiku-4-5": {
        "input": 0.001,
        "output": 0.005,
        "source": "https://platform.claude.com/docs/en/about-claude/pricing",
        "effective_date": "2026-08-20",
    },
}

PROVIDER_MODELS = {
    "openai": [model.strip() for model in os.getenv("OPENAI_MODELS", f"{OPENAI_MODEL_A},{OPENAI_MODEL_B}").split(",")],
    "gemini": [model.strip() for model in os.getenv("GEMINI_MODELS", f"{GEMINI_MODEL_A},{GEMINI_MODEL_B}").split(",")],
    "anthropic": [
        model.strip() for model in os.getenv("ANTHROPIC_MODELS", f"{ANTHROPIC_MODEL_A},{ANTHROPIC_MODEL_B}").split(",")
    ],
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
    detail = estimate_cost_detail(model_name, input_tokens, output_tokens)
    return float(detail["cost"] or 0.0)


def estimate_cost_detail(model_name: str, input_tokens: int, output_tokens: int) -> dict:
    pricing = TOKEN_PRICING_PER_1K.get(model_name)
    if model_name == "mock-model":
        return {
            "cost": 0.0,
            "pricing_version": PRICING_VERSION,
            "pricing_source": "synthetic",
            "pricing_effective_date": pricing["effective_date"] if pricing else PRICING_EFFECTIVE_DATE,
            "pricing_expires_on": None,
            "warning": None,
        }
    if not pricing:
        return {
            "cost": None,
            "pricing_version": PRICING_VERSION,
            "pricing_source": None,
            "pricing_effective_date": None,
            "pricing_expires_on": None,
            "warning": f"No pricing is configured for exact model {model_name}; no cost was attributed.",
        }
    warning = None
    try:
        effective_date = str(pricing.get("effective_date") or PRICING_EFFECTIVE_DATE)
        age_days = (date.today() - date.fromisoformat(effective_date)).days
        if age_days > 90:
            warning = f"Pricing configuration is {age_days} days old and may be stale."
        expires_on = str(pricing.get("expires_on") or "")
        if expires_on and date.today() > date.fromisoformat(expires_on):
            warning = (
                f"Pricing configuration expired on {expires_on}; no readiness decision should rely on this estimate."
            )
    except ValueError:
        warning = "Pricing effective date is invalid."
    cost = (input_tokens / 1000.0) * float(pricing["input"]) + (output_tokens / 1000.0) * float(pricing["output"])
    return {
        "cost": round(cost, 8),
        "pricing_version": PRICING_VERSION,
        "pricing_source": pricing.get("source"),
        "pricing_effective_date": pricing.get("effective_date") or PRICING_EFFECTIVE_DATE,
        "pricing_expires_on": pricing.get("expires_on"),
        "warning": warning,
    }


def approx_tokens(text: str) -> int:
    words = len((text or "").split())
    return max(1, int(words * 1.3))
