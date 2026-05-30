from __future__ import annotations

from pathlib import Path

import pandas as pd

from src import config
from src.chunker import chunk_documents
from src.document_loader import load_documents


def sample_document_paths() -> list[Path]:
    return sorted(config.SAMPLE_DOCS_DIR.glob("*.md"))


def load_sample_documents() -> tuple[list[dict], list[dict]]:
    documents = load_documents(sample_document_paths())
    chunks = chunk_documents(documents)
    return documents, chunks


def load_sample_eval_dataset() -> pd.DataFrame:
    return pd.read_csv(config.DATA_DIR / "eval_questions.csv")


def load_prompt(path_name: str) -> str:
    return (config.PROMPTS_DIR / path_name).read_text(encoding="utf-8")


def default_prompts() -> dict[str, str]:
    return {
        "Current Prompt": load_prompt("current_prompt_sample.md"),
        "Improved Prompt": load_prompt("improved_prompt_template.md"),
    }


def sample_project_metadata() -> dict[str, str]:
    return {
        "name": "FinSure Assistant QA",
        "company": "FinSure",
        "industry": "Fintech / Digital Lending",
        "use_case": "Customer support assistant for refunds, KYC, loan rejection, account closure, and escalation queries",
        "notes": "Fictional demo project for testing whether a fintech support assistant is reliable enough for launch.",
    }
