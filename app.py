from __future__ import annotations

# ruff: noqa: E402
# Public-session defaults must be set before application configuration is imported.
import html
import json
import os
from copy import deepcopy
from pathlib import Path

import pandas as pd
import streamlit as st

os.environ.setdefault("AUTH_MODE", "public-session")

from src import charts, config, database
from src.aggregation import compare_candidates, evaluate_candidates
from src.calibration import (
    DEFAULT_CALIBRATION_LABELS,
    CalibrationRequirements,
    EvaluatorThresholdConfiguration,
    read_calibration_dataset,
    run_calibration_workflow,
)
from src.chunker import chunk_documents
from src.datasets import coverage_analysis, dataset_quality_report, validate_dataset_frame
from src.document_loader import UPLOAD_TYPES, detect_duplicate_documents, load_uploaded_document
from src.evaluator import EVALUATION_UPLOAD_TYPES, normalize_eval_dataset, read_eval_dataset, run_evaluation
from src.presentation import execution_summary, failure_presentation, safe_display_text, safe_nested
from src.public_sessions import end_public_session, initialize_session
from src.reporting import csv_report, html_report, json_report
from src.sample_data import (
    default_prompts,
    load_sample_documents,
    load_sample_eval_dataset,
    sample_project_metadata,
)
from src.saved_responses import compare_response_reviews, read_response_file
from src.scoring import EVALUATOR_VERSION
from src.security import privacy_notice, validate_upload_batch
from src.suggestions import generate_improved_prompt, prompt_change_proposal
from src.targets import ExternalHTTPTarget, ExternalTargetConfig, SecretResolver
from src.ui_workflows import (
    REVIEW_LABELS,
    evaluate_review_workspace,
    new_review_workspace,
    optional_review_text,
    read_reference_json,
    read_reference_uploads,
    read_review_workspace,
    replacement_batch,
    sample_replacements,
    sample_review_workspace,
    save_case_review,
    starter_pack,
    utc_now_text,
)
from src.vector_store import SimpleVectorStore

st.set_page_config(page_title="AI Reliability Studio", page_icon="ARS", layout="wide")

PROVIDER_LABELS = {"OpenAI": "openai", "Google Gemini": "gemini", "Anthropic Claude": "anthropic"}
PROVIDER_SECRET_NAMES = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ars-text: #182230;
            --ars-muted: #46515f;
            --ars-subtle: #687385;
            --ars-panel: #ffffff;
            --ars-page: #fbfcfe;
            --ars-border: #e6e8ef;
        }
        .stApp,
        [data-testid="stAppViewContainer"],
        .block-container {
            background: var(--ars-page);
            color: var(--ars-text);
        }
        .block-container {padding-top: 4.5rem; padding-bottom: 2rem; max-width: 1440px;}
        [data-testid="stSidebar"] {
            background: #f7f8fb;
            color: var(--ars-text);
        }
        [data-testid="stSidebar"] * {
            color: var(--ars-text);
        }
        header,
        .stAppHeader,
        .stAppToolbar,
        .stAppHeader *,
        .stAppToolbar *,
        .stAppDeployButton,
        .stAppDeployButton * {
            color: var(--ars-text) !important;
        }
        header, .stAppHeader {background: var(--ars-page) !important;}
        .stAppHeader button,
        .stAppToolbar button,
        .stAppDeployButton button {
            color: var(--ars-text) !important;
            border-color: var(--ars-border) !important;
        }
        .stMarkdown,
        .stMarkdown *,
        label,
        p,
        span,
        h1,
        h2,
        h3,
        h4,
        h5,
        h6 {
            color: var(--ars-text);
        }
        .hero {
            padding: 1.35rem 1.5rem;
            border: 1px solid var(--ars-border);
            border-radius: 8px;
            background: linear-gradient(135deg, #ffffff 0%, #f7fbfa 58%, #f8f6ff 100%);
            margin-bottom: 1rem;
            color: var(--ars-text);
        }
        .hero h1 {font-size: 2rem; margin: 0 0 .35rem 0; letter-spacing: 0; color: var(--ars-text);}
        .hero p {font-size: 1rem; margin: .2rem 0; color: var(--ars-muted);}
        div[data-testid="stMetric"] {
            border: 1px solid var(--ars-border);
            border-radius: 8px;
            padding: .8rem 1rem;
            background: var(--ars-panel);
            color: var(--ars-text);
        }
        div[data-testid="stMetric"] *,
        [data-testid="stMetricLabel"],
        [data-testid="stMetricValue"],
        [data-testid="stMetricDelta"] {
            color: var(--ars-text) !important;
        }
        .mode-pill {
            display: inline-block;
            border: 1px solid #d7dce5;
            border-radius: 999px;
            padding: .25rem .65rem;
            background: var(--ars-panel);
            color: #344054 !important;
            font-size: .85rem;
        }
        .stAlert,
        [data-testid="stExpander"],
        [data-testid="stDataFrame"],
        [data-testid="stTable"],
        [data-testid="stForm"],
        [data-testid="stFileUploader"],
        [data-testid="stTextInput"],
        [data-testid="stTextArea"],
        [data-testid="stSelectbox"],
        [data-testid="stMultiSelect"],
        [data-testid="stNumberInput"] {
            color: var(--ars-text);
        }
        [data-testid="stFileUploaderDropzone"] {
            background: var(--ars-panel) !important;
            border: 1px dashed var(--ars-border) !important;
        }
        [data-testid="stFileUploaderDropzone"] * {
            color: var(--ars-text) !important;
        }
        input,
        textarea,
        select,
        [data-baseweb="input"],
        [data-baseweb="textarea"],
        [data-baseweb="select"],
        [data-baseweb="popover"],
        [data-baseweb="menu"] {
            background-color: var(--ars-panel) !important;
            color: var(--ars-text) !important;
        }
        input::placeholder,
        textarea::placeholder {
            color: var(--ars-subtle) !important;
            opacity: 1;
        }
        [data-testid="stMultiSelect"] [data-baseweb="select"],
        [data-testid="stMultiSelect"] div[data-baseweb="select"] > div {
            background: #ffffff !important;
            border-color: #cfd5df !important;
            color: var(--ars-text) !important;
        }
        [data-testid="stMultiSelect"] input,
        [data-testid="stMultiSelect"] [data-baseweb="input"],
        [data-testid="stMultiSelect"] [data-baseweb="input"] *,
        [data-testid="stMultiSelect"] [contenteditable="true"] {
            background: transparent !important;
            color: var(--ars-text) !important;
            caret-color: var(--ars-text) !important;
        }
        [data-testid="stMultiSelect"] [data-baseweb="tag"] {
            background: #eaf1ff !important;
            border: 1px solid #bdd0f7 !important;
            border-radius: 6px !important;
            color: #17324d !important;
            max-width: 100% !important;
        }
        [data-testid="stMultiSelect"] [data-baseweb="tag"] *,
        [data-testid="stMultiSelect"] [data-baseweb="tag"] span,
        [data-testid="stMultiSelect"] [data-baseweb="tag"] svg {
            background: transparent !important;
            color: #17324d !important;
            fill: #17324d !important;
            stroke: #17324d !important;
            text-shadow: none !important;
        }
        [data-testid="stMultiSelect"] svg {
            color: var(--ars-text) !important;
            fill: var(--ars-text) !important;
        }
        button[kind="secondary"],
        button[data-testid="stBaseButton-secondary"],
        button[kind="minimal"],
        button[data-testid="stBaseButton-minimal"],
        .stDownloadButton button {
            background: var(--ars-panel) !important;
            color: var(--ars-text) !important;
            border-color: #cfd5df !important;
        }
        button[kind="secondary"] *,
        button[data-testid="stBaseButton-secondary"] *,
        button[kind="minimal"] *,
        button[data-testid="stBaseButton-minimal"] *,
        .stDownloadButton button * {
            color: var(--ars-text) !important;
        }
        button[kind="primary"],
        button[data-testid="stBaseButton-primary"] {
            background: #174ea6 !important;
            border-color: #174ea6 !important;
            color: #ffffff !important;
        }
        button[kind="primary"] *,
        button[data-testid="stBaseButton-primary"] * {
            color: #ffffff !important;
        }
        [data-testid="stDataFrame"] *,
        [data-testid="stTable"] * {
            color: var(--ars-text);
        }
        .chunk-text {
            background: #f8fafc;
            border: 1px solid #dfe5ee;
            border-radius: 8px;
            color: var(--ars-text);
            font-size: .92rem;
            line-height: 1.48;
            max-height: 260px;
            overflow: auto;
            padding: .75rem .85rem;
            white-space: pre-wrap;
            word-break: break-word;
        }
        .chunk-text * {
            color: var(--ars-text) !important;
            font-size: .92rem !important;
            line-height: 1.48 !important;
            margin: 0 !important;
        }
        [data-testid="stExpander"] details,
        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] summary:hover,
        [data-testid="stExpander"] summary:focus,
        [data-testid="stExpander"] summary:active,
        [data-testid="stExpander"] details[open] summary {
            background: #ffffff !important;
            color: var(--ars-text) !important;
            border-color: #dfe5ee !important;
        }
        [data-testid="stExpander"] summary *,
        [data-testid="stExpander"] summary:hover *,
        [data-testid="stExpander"] summary:focus *,
        [data-testid="stExpander"] summary:active *,
        [data-testid="stExpander"] details[open] summary * {
            background: transparent !important;
            color: var(--ars-text) !important;
            text-shadow: none !important;
        }
        [data-testid="stExpander"] details[open] {
            background: #ffffff !important;
        }
        [data-testid="stJson"],
        [data-testid="stJson"] .react-json-view,
        [data-testid="stJson"] .pretty-json-container,
        [data-testid="stJson"] .object-container,
        [data-testid="stJson"] .array-container,
        [data-testid="stJson"] .object-content,
        [data-testid="stJson"] .pushed-content,
        [data-testid="stJson"] .variable-row,
        [data-testid="stJson"] .variable-value {
            background: #f8fafc !important;
            color: var(--ars-text) !important;
        }
        [data-testid="stJson"] {
            border: 1px solid #dfe5ee;
            border-radius: 8px;
            overflow: hidden;
            padding: .65rem .75rem;
        }
        [data-testid="stJson"] *,
        [data-testid="stJson"] span,
        [data-testid="stJson"] div {
            color: var(--ars-text) !important;
            font-size: .88rem !important;
            line-height: 1.45 !important;
            text-shadow: none !important;
        }
        [data-testid="stJson"] .variable-value,
        [data-testid="stJson"] .string-value,
        [data-testid="stJson"] .number-value,
        [data-testid="stJson"] .boolean-value {
            color: #0f766e !important;
        }
        [data-testid="stCodeBlock"],
        [data-testid="stCodeBlock"] pre,
        [data-testid="stCodeBlock"] code,
        pre,
        pre code {
            background: #f8fafc !important;
            border-color: #dfe5ee !important;
            color: var(--ars-text) !important;
        }
        [data-testid="stCodeBlock"] *,
        pre *,
        pre code *,
        code[class*="language-"] *,
        code[class*="language-"] {
            background: transparent !important;
            color: var(--ars-text) !important;
            font-size: .86rem !important;
            line-height: 1.45 !important;
            text-shadow: none !important;
        }
        [data-testid="stCodeBlock"] pre,
        pre {
            border: 1px solid #dfe5ee !important;
            border-radius: 8px !important;
            padding: .75rem .85rem !important;
        }
        [data-testid="stElementToolbar"],
        [data-testid="stElementToolbar"] *,
        button[kind="elementToolbar"],
        button[data-testid="stBaseButton-elementToolbar"],
        button[kind="elementToolbar"] *,
        button[data-testid="stBaseButton-elementToolbar"] * {
            color: var(--ars-text) !important;
            fill: var(--ars-text) !important;
            stroke: var(--ars-text) !important;
        }
        [data-testid="stElementToolbar"],
        button[kind="elementToolbar"],
        button[data-testid="stBaseButton-elementToolbar"] {
            display: none !important;
            opacity: 0 !important;
            pointer-events: none !important;
        }
        [role="tooltip"],
        [data-baseweb="tooltip"],
        [data-testid="stTooltipContent"],
        [data-baseweb="popover"],
        [data-baseweb="menu"],
        div[class*="tooltip"],
        div[class*="Tooltip"],
        div[class*="popover"],
        div[class*="Popover"] {
            background: #ffffff !important;
            border: 1px solid #dfe5ee !important;
            border-radius: 8px !important;
            color: var(--ars-text) !important;
            box-shadow: 0 10px 26px rgba(16, 24, 40, .14) !important;
        }
        [role="tooltip"] *,
        [data-baseweb="tooltip"] *,
        [data-testid="stTooltipContent"] *,
        [data-baseweb="popover"] *,
        [data-baseweb="menu"] *,
        div[class*="tooltip"] *,
        div[class*="Tooltip"] *,
        div[class*="popover"] *,
        div[class*="Popover"] * {
            background: transparent !important;
            color: var(--ars-text) !important;
            fill: var(--ars-text) !important;
            stroke: var(--ars-text) !important;
            text-shadow: none !important;
        }
        button:focus-visible,
        input:focus-visible,
        textarea:focus-visible,
        [role="radio"]:focus-visible,
        [role="checkbox"]:focus-visible,
        [role="combobox"]:focus-visible {
            outline: 3px solid #0f766e !important;
            outline-offset: 2px !important;
        }
        @media (max-width: 768px) {
            .block-container {
                padding-left: .8rem !important;
                padding-right: .8rem !important;
            }
            [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
                gap: .75rem !important;
            }
            [data-testid="column"] {
                flex: 1 1 100% !important;
                min-width: min(100%, 18rem) !important;
                width: 100% !important;
            }
            [data-testid="stMetricValue"] {
                font-size: 1.55rem !important;
            }
            [data-testid="stDataFrame"],
            [data-testid="stTable"] {
                overflow-x: auto !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def request_headers() -> dict:
    try:
        return dict(st.context.headers)
    except Exception:
        return {}


def bind_current_session():
    return initialize_session(st.session_state, request_headers())


def audited_export(format_name, payload, run_id) -> None:
    bind_current_session()
    database.record_export(format_name, payload, run_id)


def init_state() -> None:
    session = bind_current_session()
    database.init_db()
    authenticated_context = session.context
    st.session_state.public_session_notice = session.notice if session.ephemeral else ""
    prompts = default_prompts()
    st.session_state.setdefault("mode", "Demo Mode")
    st.session_state.setdefault("openai_api_key", "")
    st.session_state.setdefault("api_provider", "OpenAI")
    st.session_state.setdefault(
        "provider_api_keys",
        {"openai": st.session_state.get("openai_api_key", ""), "gemini": "", "anthropic": ""},
    )
    st.session_state.setdefault("project_id", None)
    st.session_state.setdefault("workspace_context", authenticated_context)
    if "calibration_result" not in st.session_state:
        threshold_version = EvaluatorThresholdConfiguration().version
        latest_calibration = database.get_repository().latest_calibration(
            authenticated_context,
            threshold_version=threshold_version,
        )
        st.session_state.calibration_result = (
            latest_calibration.get("result") if latest_calibration is not None else None
        )
    st.session_state.setdefault("project", sample_project_metadata())
    st.session_state.setdefault("documents", [])
    st.session_state.setdefault("chunks", database.load_chunks())
    st.session_state.setdefault("eval_df", pd.DataFrame())
    st.session_state.setdefault(
        "calibration_reviews_df",
        pd.DataFrame(columns=["case_id", "split", "human_labels", "automatic_labels", "notes"]),
    )
    st.session_state.setdefault("current_prompt", prompts["Current Prompt"])
    st.session_state.setdefault("improved_prompt", prompts["Improved Prompt"])
    st.session_state.setdefault("last_results", charts.prepare_results(database.latest_results_df()))
    st.session_state.setdefault("last_top_k", config.DEFAULT_TOP_K)
    st.session_state.setdefault("similarity_threshold", config.DEFAULT_SIMILARITY_THRESHOLD)
    st.session_state.setdefault("external_target_config", {})
    st.session_state.setdefault("external_target_secret", "")
    st.session_state.setdefault("privacy_acknowledged", False)


def load_demo() -> None:
    metadata = sample_project_metadata()
    project_id = database.save_project(metadata)
    documents, chunks = load_sample_documents()
    prompts = default_prompts()
    st.session_state.mode = "Demo Mode"
    st.session_state.project = metadata
    st.session_state.project_id = project_id
    st.session_state.documents = documents
    st.session_state.chunks = chunks
    st.session_state.eval_df = normalize_eval_dataset(load_sample_eval_dataset())
    st.session_state.current_prompt = prompts["Current Prompt"]
    st.session_state.improved_prompt = prompts["Improved Prompt"]
    st.session_state.last_results = pd.DataFrame()
    database.save_documents_and_chunks(documents, chunks, project_id=project_id)
    database.save_prompt(project_id, "Current Prompt", prompts["Current Prompt"], "current")
    database.save_prompt(project_id, "Improved Prompt", prompts["Improved Prompt"], "improved")


def effective_api_key() -> str:
    provider = selected_provider()
    if public_session_mode():
        return (st.session_state.get("provider_api_keys", {}).get(provider) or "").strip()
    return (
        (st.session_state.get("provider_api_keys", {}).get(provider) or "").strip()
        or streamlit_secret_api_key(provider)
        or config.api_key_for_provider(provider)
    )


def api_key_source() -> str:
    provider = selected_provider()
    if (st.session_state.get("provider_api_keys", {}).get(provider) or "").strip():
        return "In-app session key"
    if public_session_mode():
        return "No session API key"
    if streamlit_secret_api_key(provider):
        return "Streamlit secrets"
    if config.api_key_for_provider(provider):
        return ".env key"
    return "No API key"


def api_key_status_label() -> str:
    return "Available" if effective_api_key() else "Not available"


def model_options() -> list[str]:
    return config.available_models(api_key=effective_api_key(), provider=selected_provider())


def selected_provider() -> str:
    return PROVIDER_LABELS.get(st.session_state.get("api_provider", "OpenAI"), "openai")


def streamlit_secret_api_key(provider: str | None = None) -> str:
    if public_session_mode():
        return ""
    if not _streamlit_secrets_file_exists():
        return ""
    secret_name = PROVIDER_SECRET_NAMES[provider or selected_provider()]
    try:
        return str(st.secrets.get(secret_name, "") or "").strip()
    except Exception:
        return ""


def _streamlit_secrets_file_exists() -> bool:
    if public_session_mode():
        return False
    configured = os.getenv("STREAMLIT_SECRETS_FILE", "").strip()
    candidates = [
        Path(configured).expanduser() if configured else None,
        config.ROOT_DIR / ".streamlit" / "secrets.toml",
        Path.home() / ".streamlit" / "secrets.toml",
    ]
    return any(path is not None and path.is_file() for path in candidates)


def public_session_mode() -> bool:
    check = getattr(config, "public_sessions_enabled", None)
    return bool(check()) if check is not None else os.getenv("AUTH_MODE", "").lower() == "public-session"


def external_connections_available() -> bool:
    return not public_session_mode() or bool(config.EXTERNAL_TARGET_ALLOWED_HOSTS)


def start_custom_mode() -> None:
    st.session_state.mode = "Custom Upload Mode"
    st.session_state.project = {
        "name": "Custom Assistant QA",
        "company": "",
        "industry": "",
        "use_case": "",
        "notes": "",
    }
    st.session_state.project_id = None
    st.session_state.documents = []
    st.session_state.chunks = []
    st.session_state.eval_df = pd.DataFrame()
    st.session_state.current_prompt = default_prompts()["Current Prompt"]
    st.session_state.improved_prompt = generate_improved_prompt(st.session_state.current_prompt)
    st.session_state.last_results = pd.DataFrame()


def save_uploaded_documents(files) -> int:
    validate_upload_batch(len(files))
    documents = []
    for uploaded in files:
        try:
            document = load_uploaded_document(uploaded)
            documents.append(document)
            for warning in document.get("warnings", []):
                st.warning(f"{document['filename']}: {warning}")
        except Exception as exc:
            st.warning(f"{uploaded.name} skipped: {exc}")
    if documents:
        duplicates = detect_duplicate_documents(documents)
        for duplicate in duplicates:
            st.warning(
                f"{duplicate['document']} is a {duplicate['type']} duplicate of {duplicate['duplicate_of']} "
                f"(similarity {duplicate['similarity']:.2f}). Exact duplicates are skipped; review near duplicates."
            )
        chunks = chunk_documents(documents)
        st.session_state.documents = documents
        st.session_state.chunks = chunks
        database.save_documents_and_chunks(documents, chunks, project_id=st.session_state.project_id)
    return len(documents)


def bool_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin(["true", "1", "yes", "y"])


def parse_jsonish(value):
    if isinstance(value, list | dict):
        return value
    try:
        return json.loads(value)
    except Exception:
        return []


def render_plain_text(text: str) -> None:
    safe = html.escape(safe_display_text(text))
    st.markdown(f"<div class='chunk-text'>{safe}</div>", unsafe_allow_html=True)


def safe_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    records = frame.where(pd.notna(frame), None).to_dict(orient="records")
    return pd.DataFrame([safe_nested(record) for record in records])


def navigate_to(page: str, message: str = "") -> None:
    st.session_state._next_page = page
    if message:
        st.session_state._workflow_message = message
    st.rerun()


def install_review_workspace(workspace: dict) -> None:
    baseline = evaluate_review_workspace(workspace)
    candidate = evaluate_review_workspace(workspace, "candidate")
    st.session_state.offline_workspace = workspace
    st.session_state.offline_baseline = baseline
    st.session_state.offline_candidate = candidate
    st.session_state._offline_batch_request = "Original answers"


def workflow_error(error: Exception, action: str = "import these files") -> None:
    st.error(f"We couldn't {action}. Check the details below, correct the input, and try again.")
    st.caption(safe_display_text(str(error)))


def submit_saved_case_review(batch: str, case_id: str, form_suffix: str) -> None:
    """Handle a form before rendering so advancing cases never reuses stale widgets."""
    bind_current_session()
    if not st.session_state.get("offline_workspace"):
        st.session_state._workflow_warning = "This session ended. Restore your workspace download to continue."
        return
    frame = st.session_state[f"offline_{batch}"]
    row = frame[frame["case_id"] == case_id].iloc[0].to_dict()
    decision = st.session_state.get(f"review_decision_{form_suffix}")
    note = optional_review_text(st.session_state.get(f"review_note_{form_suffix}"))
    reviewer = optional_review_text(st.session_state.get(f"reviewer_{form_suffix}"))
    checked = st.session_state.get(f"review_checked_{form_suffix}", False)
    allowed = (
        ["execution_error"] if row.get("execution_status") != "passed" else ["supported", "failed", "inconclusive"]
    )
    selected = next((value for value in allowed if REVIEW_LABELS[value] == decision), None)
    if selected is None or not note.strip() or not reviewer.strip() or not checked:
        st.session_state._workflow_warning = (
            "Choose a decision, explain it, add your name, and confirm that you checked the evidence."
        )
        return
    review = {key: row[key] for key in ("case_id", "response_hash", "case_version", "knowledge_base_version")}
    review.update(
        decision=selected,
        note=note,
        reviewer=reviewer,
        reviewer_kind="ai_assisted"
        if st.session_state.get(f"review_method_{form_suffix}") == "Reviewed with AI assistance"
        else "human",
    )
    try:
        updated, reviewed = save_case_review(st.session_state.offline_workspace, batch, frame, review)
        st.session_state.offline_workspace = updated
        st.session_state[f"offline_{batch}"] = reviewed
        st.session_state.saved_reviewer_name = reviewer
        remaining = reviewed[reviewed["review_status"] != "reviewed"]["case_id"].tolist()
        if remaining:
            st.session_state[f"_next_saved_case_{batch}"] = remaining[0]
        st.session_state._workflow_message = f"Review saved. {len(remaining)} answers remain in this batch."
    except Exception as exc:
        st.session_state._workflow_warning = f"The review could not be saved: {safe_display_text(str(exc))}"


def add_replacement_answers(*, sample: bool = False) -> None:
    bind_current_session()
    workspace = st.session_state.get("offline_workspace")
    if not workspace:
        st.session_state._workflow_warning = "This session ended. Restore your workspace download to continue."
        return
    try:
        if sample:
            responses = sample_replacements(workspace)
            version, captured = "fictional-v2", utc_now_text()
        else:
            uploaded = st.session_state.get("replacement_upload")
            version = st.session_state.get("replacement_version", "")
            captured = st.session_state.get("replacement_captured", "")
            if uploaded is None or not version.strip() or not captured.strip():
                st.session_state._workflow_warning = "Add a replacement answer file, a version, and a capture time."
                return
            responses = read_response_file(uploaded.name, uploaded.getvalue())
        updated = deepcopy(workspace)
        updated["candidate"] = replacement_batch(responses, version, captured)
        result = evaluate_review_workspace(updated, "candidate")
        st.session_state.offline_workspace = updated
        st.session_state.offline_candidate = result
        st.session_state._offline_batch_request = "Replacement answers"
        st.session_state._workflow_message = (
            "Two authored replacement answers loaded. This demonstrates the workflow, not a real assistant improvement."
            if sample
            else f"Imported {len(result)} replacement answers. Review them before interpreting the comparison."
        )
    except Exception as exc:
        st.session_state._workflow_warning = f"The replacements could not be imported: {safe_display_text(str(exc))}"


def render_overview() -> None:
    st.markdown(
        """
        <div class="hero">
          <h1>AI Reliability Studio</h1>
          <p><strong>Check an assistant's answers against your sources.</strong></p>
          <p>Bring saved answers or connect an assistant. Review the evidence, record your findings, and check what changed after a fix.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns(3)
    with c1, st.container(border=True):
        st.subheader("See how it works")
        st.write("Review three fictional answers and try a replacement batch. No API key needed.")
        if st.button("Try sample", type="primary", use_container_width=True, key="start_sample"):
            load_demo()
            install_review_workspace(sample_review_workspace())
            navigate_to("Review saved answers", "FinSure demo loaded. Three fictional answers are ready to review.")
    with c2, st.container(border=True):
        st.subheader("Use answers you have")
        st.write("Upload questions, source documents and saved answers. No assistant connection required.")
        if st.button("Review saved answers", use_container_width=True, key="start_saved"):
            navigate_to("Review saved answers")
    with c3, st.container(border=True):
        st.subheader("Collect new answers")
        st.write("Connect your API or a model provider, then run a set of questions you control.")
        if st.button("Evaluate live assistant", use_container_width=True, key="start_live"):
            st.session_state.live_step = "1. Sources"
            navigate_to("Evaluate live assistant")
    st.info(
        "Automatic checks help organize the evidence. They can be wrong or uncertain, so review every answer before "
        "treating a finding as confirmed. This app does not certify launch readiness."
    )
    if st.session_state.get("offline_workspace"):
        frame = st.session_state.offline_baseline
        done = int(frame["review_status"].eq("reviewed").sum())
        st.caption(f"Your current saved-answer workspace: {done} of {len(frame)} original answers reviewed.")
    with st.expander("Existing project tools"):
        st.write(
            "Project setup, prompt comparison, calibration, run history, and exports remain available in the sidebar."
        )
        if st.button("Open project setup"):
            navigate_to("Project Setup")
        if st.button("Start a new live project"):
            start_custom_mode()
            navigate_to("Evaluate live assistant")


def render_saved_import() -> None:
    st.subheader("1. Add your files")
    st.write("Use a question file with expected answers, the source documents, and the assistant's saved answers.")
    st.download_button("Download starter files", starter_pack(), "saved-answer-starter.zip", "application/zip")
    method = st.radio(
        "How would you like to add the data?", ["Upload files", "Paste JSON"], horizontal=True, key="saved_input_method"
    )
    if st.button("Use the three-answer sample", key="saved_import_sample"):
        install_review_workspace(sample_review_workspace())
        navigate_to("Review saved answers", "Three fictional answers loaded. Review their sources to try the workflow.")
    with st.form("saved_import_form"):
        source_files, dataset_file, answer_file = [], None, None
        source_text, question_text, answer_text = "", "", ""
        if method == "Upload files":
            source_files = st.file_uploader(
                "Source documents",
                type=UPLOAD_TYPES,
                accept_multiple_files=True,
                key="saved_sources_upload",
                help="For source JSON, use the passage format in the starter files. TXT, Markdown, PDF and DOCX also work.",
            )
            c1, c2 = st.columns(2)
            dataset_file = c1.file_uploader(
                "Questions and expected answers", type=EVALUATION_UPLOAD_TYPES, key="saved_questions_upload"
            )
            answer_file = c2.file_uploader(
                "Saved assistant answers", type=["json", "jsonl", "csv"], key="saved_answers_upload"
            )
        else:
            st.caption(
                "Paste JSON arrays in the same format as the starter files. Keep complete source passages and matching case IDs."
            )
            source_text = st.text_area("Source passages JSON", height=160, key="saved_sources_json")
            question_text = st.text_area("Questions JSON", height=160, key="saved_questions_json")
            answer_text = st.text_area("Answers JSON", height=160, key="saved_answers_json")
        c1, c2 = st.columns(2)
        target_name = c1.text_input("Assistant name", placeholder="Customer support assistant", key="saved_target_name")
        target_version = c2.text_input(
            "Assistant version or batch name", placeholder="Before the September update", key="saved_target_version"
        )
        captured_at = st.text_input(
            "When were these answers collected?",
            placeholder="2026-09-07T09:00:00+00:00",
            key="saved_captured_at",
            help="Include the time zone. This is the capture time you report, not a verified timestamp.",
        )
        fictional = st.checkbox("These are fictional sample answers", key="saved_fixture_flag")
        submitted = st.form_submit_button("Import answers", type="primary")
    st.caption(
        "Only import content you are permitted to review. Importing saved answers does not call a model provider."
    )
    if submitted:
        missing_upload = method == "Upload files" and (not source_files or dataset_file is None or answer_file is None)
        missing_paste = method == "Paste JSON" and not all(
            value.strip() for value in (source_text, question_text, answer_text)
        )
        if missing_upload or missing_paste:
            st.warning("Add the sources, question file, and answer file to continue.")
        elif not all(value.strip() for value in (target_name, target_version, captured_at)):
            st.warning("Add an assistant name, a version or batch name, and the capture time.")
        else:
            try:
                if method == "Upload files":
                    dataset = read_eval_dataset(dataset_file.name, dataset_file.getvalue())
                    responses = read_response_file(answer_file.name, answer_file.getvalue())
                    sources = read_reference_uploads(source_files)
                else:
                    dataset = read_eval_dataset("questions.json", question_text.encode())
                    responses = read_response_file("answers.json", answer_text.encode())
                    sources = read_reference_json(source_text.encode())
                workspace = new_review_workspace(
                    dataset,
                    sources,
                    responses,
                    target_name=target_name,
                    target_version=target_version,
                    captured_at=captured_at,
                    evidence_kind="fixture" if fictional else "client_supplied",
                )
                install_review_workspace(workspace)
                navigate_to("Review saved answers", f"Imported {len(responses)} answers. Each is pending your review.")
            except Exception as exc:
                workflow_error(exc)
    with st.expander("Resume a saved workspace"):
        saved = st.file_uploader("Workspace file exported by this app", type=["json"], key="resume_saved_workspace")
        if st.button("Resume review", disabled=saved is None):
            try:
                install_review_workspace(read_review_workspace(saved.getvalue()))
                navigate_to(
                    "Review saved answers",
                    "Workspace restored. Existing review hashes were checked against its inputs.",
                )
            except Exception as exc:
                workflow_error(exc, "restore this workspace")


def render_saved_case_review(workspace: dict, batch: str, frame: pd.DataFrame) -> None:
    pending = frame[frame["review_status"] != "reviewed"]["case_id"].tolist()
    choices = frame["case_id"].tolist()
    selection_key = f"saved_case_{batch}"
    requested = st.session_state.pop(f"_next_saved_case_{batch}", None)
    if requested in choices:
        st.session_state[selection_key] = requested
    if st.session_state.get(selection_key) not in choices:
        st.session_state[selection_key] = pending[0] if pending else choices[0]
    questions = frame.set_index("case_id")["question"].to_dict()
    selected = st.selectbox(
        "Answer to review",
        choices,
        format_func=lambda value: f"{'Pending' if value in pending else 'Reviewed'} · {value} · {safe_display_text(questions[value])}",
        key=selection_key,
    )
    row = frame[frame["case_id"] == selected].iloc[0].to_dict()
    expected_case = next(case for case in workspace["dataset"] if str(case["case_id"]) == str(selected))
    st.subheader(safe_display_text(row["question"]))
    left, right = st.columns([1, 1])
    with left:
        st.markdown("**Assistant answer**")
        render_plain_text(row.get("actual_answer", ""))
        if row.get("execution_status") != "passed":
            st.warning(
                "The assistant did not complete this answer. Record an execution error separately from answer quality."
            )
        action = row.get("structured_escalation") or {}
        if action.get("should_escalate"):
            st.write(
                f"Returned action: escalate to {safe_display_text(action.get('destination', 'not specified'))}; urgency {safe_display_text(action.get('urgency', 'not specified'))}."
            )
        citations = row.get("provided_citations") or []
        st.caption(f"Citations returned: {len(citations)}")
        if citations:
            with st.expander("Inspect the returned citations"):
                st.json(safe_nested(citations))
        with st.expander("Automatic check · advisory only"):
            st.write(safe_display_text(row.get("failure_type", "Not available")))
            st.caption(
                "This result is not your review decision. A high score does not prove that the answer is correct."
            )
            st.json(safe_nested(row.get("score_explanation", {})))
    with right:
        st.markdown("**Expected answer**")
        render_plain_text(expected_case.get("expected_answer", ""))
        if expected_case.get("should_escalate"):
            st.caption(
                f"Expected routing: {expected_case.get('escalation_destination') or 'escalate'} · {expected_case.get('escalation_urgency') or 'urgency not specified'}"
            )
        st.markdown("**Source evidence**")
        expected_ids = set(expected_case.get("expected_passages") or [])
        sources = workspace["sources"]
        relevant = [chunk for chunk in sources if chunk.get("chunk_id") in expected_ids] if expected_ids else sources
        if not relevant:
            st.warning("No matching expected passage was found. Inspect all sources before deciding.")
        for chunk in relevant:
            with st.expander(
                f"{safe_display_text(chunk['source_name'])} · {safe_display_text(chunk.get('section') or chunk['chunk_id'])}",
                expanded=len(relevant) <= 2,
            ):
                st.caption(f"Passage ID: {safe_display_text(chunk['chunk_id'])}")
                render_plain_text(chunk["chunk_text"])
        if expected_ids:
            with st.expander("All uploaded sources"):
                for chunk in sources:
                    st.markdown(
                        f"**{safe_display_text(chunk['source_name'])} · {safe_display_text(chunk['chunk_id'])}**"
                    )
                    render_plain_text(chunk["chunk_text"])
    form_suffix = f"{batch}_{selected}_{row['response_hash'][:12]}"
    with st.form(f"review_form_{form_suffix}"):
        st.markdown("**Your review**")
        allowed = (
            ["execution_error"] if row.get("execution_status") != "passed" else ["supported", "failed", "inconclusive"]
        )
        labels = ["Choose a decision", *[REVIEW_LABELS[value] for value in allowed]]
        existing_decision = REVIEW_LABELS.get(optional_review_text(row.get("review_decision")), "Choose a decision")
        st.selectbox(
            "Decision",
            labels,
            index=labels.index(existing_decision) if existing_decision in labels else 0,
            key=f"review_decision_{form_suffix}",
        )
        st.text_area(
            "What in the source supports your decision?",
            value=optional_review_text(row.get("review_note")),
            placeholder="Describe the relevant passage, mismatch, or missing evidence.",
            key=f"review_note_{form_suffix}",
        )
        c1, c2 = st.columns(2)
        c1.text_input(
            "Reviewer name",
            value=optional_review_text(row.get("reviewer"))
            or optional_review_text(st.session_state.get("saved_reviewer_name")),
            key=f"reviewer_{form_suffix}",
        )
        c2.selectbox(
            "Review method",
            ["Reviewed by me", "Reviewed with AI assistance"],
            index=int(optional_review_text(row.get("reviewer_kind")) == "ai_assisted"),
            key=f"review_method_{form_suffix}",
        )
        st.checkbox(
            "I checked this answer and its returned actions against the source evidence.",
            key=f"review_checked_{form_suffix}",
        )
        st.form_submit_button(
            "Save review and continue",
            type="primary",
            on_click=submit_saved_case_review,
            args=(batch, selected, form_suffix),
        )


def render_saved_retest(workspace: dict, baseline: pd.DataFrame, candidate: pd.DataFrame) -> None:
    st.subheader("3. Check replacement answers")
    st.caption(
        "Optional: upload answers for any subset of the original case IDs. The questions and sources stay fixed for a fair comparison."
    )
    with st.expander(
        "Add replacement answers", expanded=bool(baseline["review_status"].eq("reviewed").all() and candidate.empty)
    ):
        uploaded = st.file_uploader("Replacement answer file", type=["json", "jsonl", "csv"], key="replacement_upload")
        c1, c2 = st.columns(2)
        c1.text_input("Replacement version or batch name", key="replacement_version")
        c2.text_input(
            "Replacement capture time with time zone",
            placeholder="2026-09-07T10:00:00+00:00",
            key="replacement_captured",
        )
        st.button("Import replacements", disabled=uploaded is None, on_click=add_replacement_answers)
        if workspace.get("evidence_kind") == "fixture" and workspace.get("target_name") == "FinSure sample assistant":
            st.button(
                "Try two fictional replacements",
                key="sample_replacements",
                on_click=add_replacement_answers,
                kwargs={"sample": True},
            )
    if not candidate.empty:
        comparison = compare_response_reviews(baseline, candidate)
        reviewed = candidate["review_status"].eq("reviewed").sum()
        st.write(
            f"{len(candidate)} replacement answers · {reviewed} reviewed · {len(baseline) - len(candidate)} original cases not retested"
        )
        friendly = {
            "resolved": "Resolved",
            "regressed": "Regressed",
            "unchanged": "Unchanged",
            "pending_review": "Pending review",
            "inconclusive": "Cannot determine",
            "not_comparable": "Not comparable",
            "review_decision_changed": "Review changed; answer unchanged",
            "execution_recovered": "Execution recovered",
            "execution_failed": "Execution failed",
        }
        table = pd.DataFrame(comparison["compared_cases"])
        table["status"] = table["status"].map(lambda value: friendly.get(value, value))
        st.dataframe(
            safe_dataframe(table[["case_id", "status", "baseline_decision", "candidate_decision", "reason"]]),
            hide_index=True,
            use_container_width=True,
        )
        st.caption(
            "Changes reflect explicit reviews of the supplied answers. They do not prove a deployed improvement."
        )
        st.download_button(
            "Download comparison", json.dumps(comparison, indent=2), "answer-comparison.json", "application/json"
        )


def render_saved_answers() -> None:
    st.title("Review saved answers")
    workspace = st.session_state.get("offline_workspace")
    if not workspace:
        st.progress(0.0, text="Step 1 of 3 · Add files, then review answers and compare replacements")
        render_saved_import()
        return
    baseline = st.session_state.offline_baseline
    candidate = st.session_state.offline_candidate
    if workspace["evidence_kind"] == "fixture":
        st.info(
            "Fictional sample · These answers were authored to demonstrate the workflow. They are not customer or model performance evidence."
        )
    else:
        st.info(
            "Uploaded answers · Their origin is reported by the uploader. Automatic checks are advisory; each answer needs a separate review."
        )
    options = ["Original answers"] + (["Replacement answers"] if not candidate.empty else [])
    requested = st.session_state.pop("_offline_batch_request", None)
    if requested in options:
        st.session_state.saved_batch_select = requested
    selected_batch = st.radio("Batch to review", options, horizontal=True, key="saved_batch_select")
    batch = "baseline" if selected_batch == "Original answers" else "candidate"
    frame = baseline if batch == "baseline" else candidate
    done = int(frame["review_status"].eq("reviewed").sum())
    st.progress(done / len(frame), text=f"Step 2 of 3 · {done} of {len(frame)} {selected_batch.lower()} reviewed")
    c1, c2, c3 = st.columns(3)
    c1.metric("Pending review", len(frame) - done)
    c2.metric("Needs a fix", int(frame["review_decision"].eq("failed").sum()))
    c3.metric("Cannot determine", int(frame["review_decision"].eq("inconclusive").sum()))
    if done < len(frame):
        st.caption(
            "Next: inspect the answer and source, then save your decision. Passing automatic checks do not complete a review."
        )
    else:
        st.success("This batch is reviewed. Download the report or check replacement answers below.")
    st.subheader("2. Review the evidence")
    render_saved_case_review(workspace, batch, frame)
    st.divider()
    render_saved_retest(workspace, baseline, candidate)
    st.divider()
    st.subheader("Save your work")
    st.caption(
        f"Current report: {done} reviewed, {len(frame) - done} pending. Client retrieval, latency and cost remain unknown unless supplied."
    )
    c1, c2, c3 = st.columns(3)
    c1.download_button("Download HTML report", html_report(frame), f"{batch}-answer-review.html", "text/html")
    c2.download_button("Download JSON report", json_report(frame), f"{batch}-answer-review.json", "application/json")
    c3.download_button("Download CSV report", csv_report(frame), f"{batch}-answer-review.csv", "text/csv")
    st.download_button(
        "Download workspace to resume later",
        json.dumps(workspace, indent=2, default=str),
        "saved-answer-workspace.json",
        "application/json",
        help="Contains your uploaded sources, answers and saved reviews. Keep it private and upload it through Resume a saved workspace.",
    )
    st.caption("Keep a workspace download before leaving. Browser session data may be cleared when your session ends.")
    if st.checkbox("Import another batch or resume a saved workspace", key="offline_show_import"):
        render_saved_import()


def render_live_assistant() -> None:
    st.title("Evaluate live assistant")
    st.caption("Prepare sources and questions, connect your assistant, then inspect the returned answers.")
    steps = ["1. Sources", "2. Questions", "3. Connect and run", "4. Results"]
    requested = st.session_state.pop("_next_live_step", None)
    if requested in steps:
        st.session_state.live_step = requested
    step = st.radio("Evaluation steps", steps, horizontal=True, key="live_step")
    st.progress(steps.index(step) / 3, text=step)
    if step == steps[0]:
        st.write("Add the documents that contain the answers your assistant should use.")
        files = st.file_uploader(
            "Source documents", type=UPLOAD_TYPES, accept_multiple_files=True, key="live_source_upload"
        )
        if files and st.button("Add sources", type="primary"):
            if save_uploaded_documents(files):
                st.success("Sources added. Continue to the question set.")
        if st.session_state.chunks:
            st.success(f"{len(st.session_state.chunks)} source passages ready.")
        if st.button("Next: questions", disabled=not st.session_state.chunks):
            st.session_state._next_live_step = steps[1]
            st.rerun()
        if st.checkbox("Show source and retrieval tools", key="live_source_tools"):
            render_knowledge_base()
    elif step == steps[1]:
        uploaded = st.file_uploader(
            "Question set with expected answers", type=EVALUATION_UPLOAD_TYPES, key="live_questions_upload"
        )
        if uploaded:
            try:
                st.session_state.eval_df = read_eval_dataset(uploaded.name, uploaded.getvalue())
            except Exception as exc:
                workflow_error(exc, "read the question set")
        frame = st.session_state.eval_df
        if not frame.empty:
            st.write(f"{len(frame)} questions ready.")
            st.dataframe(
                safe_dataframe(
                    frame[[column for column in ("case_id", "question", "expected_answer") if column in frame]]
                ),
                hide_index=True,
                use_container_width=True,
            )
        st.download_button(
            "Download example question set",
            json.dumps(sample_review_workspace()["dataset"], indent=2),
            "example-questions.json",
            "application/json",
        )
        if st.button("Next: connect and run", disabled=frame.empty):
            st.session_state._next_live_step = steps[2]
            st.rerun()
        with st.expander("Edit questions and inspect coverage"):
            render_eval_dataset()
    elif step == steps[2]:
        with st.expander(
            "Connect an assistant API",
            expanded=external_connections_available()
            and not bool(st.session_state.external_target_config.get("endpoint")),
        ):
            render_target_setup()
        with st.expander(
            "Use a model provider or edit the system prompt", expanded=not external_connections_available()
        ):
            st.write(
                "For a direct model, add your session API key in Settings. API requests and provider calls only run when you explicitly start them."
            )
            if st.button("Open provider settings"):
                navigate_to("Settings / Export")
            render_system_prompt()
        render_run_evaluation(live_only=True)
        if not st.session_state.last_results.empty and st.button("Next: inspect results", type="primary"):
            st.session_state._next_live_step = steps[3]
            st.rerun()
    else:
        render_results_dashboard()
        if st.checkbox("Investigate individual failures", key="live_failure_tools"):
            render_failure_analysis()
        if not st.session_state.last_results.empty and st.button("Export or compare this run"):
            navigate_to("Settings / Export")


def render_project_setup() -> None:
    st.title("Project Setup")
    workspace = st.session_state.workspace_context
    st.caption(f"Workspace {workspace.workspace_id} · role {workspace.role.value} · user {workspace.user_id}")
    projects = database.get_repository().list_projects(workspace)
    if projects:
        labels = {f"{item['name']} (#{item['id']})": item for item in projects}
        selected = st.selectbox("Active project", ["Create or use current draft", *labels])
        if selected in labels and st.button("Switch to selected project"):
            item = labels[selected]
            st.session_state.project_id = int(item["id"])
            st.session_state.project = item
            st.session_state.chunks = database.load_chunks(project_id=int(item["id"]), context=workspace)
            st.success(f"Switched to {item['name']}.")
    project = dict(st.session_state.project)
    c1, c2 = st.columns(2)
    project["name"] = c1.text_input("Project name", project.get("name", ""))
    project["company"] = c2.text_input("Company", project.get("company", ""))
    project["industry"] = c1.text_input("Industry / domain", project.get("industry", ""))
    project["use_case"] = c2.text_input("Use case", project.get("use_case", ""))
    project["notes"] = st.text_area("Notes", project.get("notes", ""), height=120)
    if st.button("Save project metadata", type="primary"):
        st.session_state.project = project
        st.session_state.project_id = database.save_project(project)
        st.success("Project metadata saved.")


def render_knowledge_base() -> None:
    st.title("Knowledge Base")
    c1, c2 = st.columns([0.38, 0.62])
    with c1:
        if st.button("Load sample documents", type="primary"):
            documents, chunks = load_sample_documents()
            st.session_state.documents = documents
            st.session_state.chunks = chunks
            database.save_documents_and_chunks(documents, chunks, project_id=st.session_state.project_id)
            st.success(f"Loaded {len(documents)} documents and {len(chunks)} chunks.")
        uploaded = st.file_uploader(
            "Upload knowledge-base documents",
            type=UPLOAD_TYPES,
            accept_multiple_files=True,
            help="Supports text, Markdown, PDF, DOCX, RTF, CSV/TSV, Excel, JSON/JSONL, HTML, XML/YAML, and PPTX.",
        )
        st.info(privacy_notice())
        st.caption(
            "Legacy .doc and image-only/scanned documents are not supported; convert them to DOCX or searchable PDF first."
        )
        if uploaded and st.button("Index uploaded documents"):
            loaded_count = save_uploaded_documents(uploaded)
            if loaded_count:
                st.success(f"Indexed {loaded_count} documents into {len(st.session_state.chunks)} chunks.")
        docs_df = database.documents_df(project_id=st.session_state.project_id)
        st.metric("Chunk count", len(st.session_state.chunks))
        if not docs_df.empty:
            st.dataframe(docs_df, hide_index=True, use_container_width=True)
    with c2:
        st.subheader("Retrieval test")
        question = st.text_input("Sample question", "Can I close my account if I have an active loan?")
        top_k = st.slider("Top chunks", 1, 8, config.DEFAULT_TOP_K, key="kb_top_k")
        threshold = st.slider(
            "Minimum hybrid similarity",
            0.0,
            1.0,
            float(st.session_state.similarity_threshold),
            0.01,
            key="kb_similarity_threshold",
        )
        if st.button("Test retrieval") and st.session_state.chunks:
            store = SimpleVectorStore()
            store.build(st.session_state.chunks)
            results = store.retrieve(question, top_k=top_k, similarity_threshold=threshold)
            st.caption(
                f"Embedding provider: {store.embedder.name}. Semantic embeddings: "
                f"{'enabled' if store.embedder.semantic else 'not configured; lightweight TF-IDF + lexical hybrid is active'}"
            )
            for chunk in results:
                with st.expander(f"{chunk['source_name']} | similarity {chunk['similarity']:.2f}"):
                    render_plain_text(chunk["chunk_text"])
        st.subheader("Chunk preview")
        preview = pd.DataFrame(st.session_state.chunks[:10])
        if not preview.empty:
            preview_columns = [
                column
                for column in ["source_name", "page", "section", "kind", "chunk_id", "chunk_index", "chunk_text"]
                if column in preview
            ]
            st.dataframe(preview[preview_columns], hide_index=True, use_container_width=True)


def render_system_prompt() -> None:
    st.title("System Prompt")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Load sample current prompt"):
            st.session_state.current_prompt = default_prompts()["Current Prompt"]
        current = st.text_area("Current system prompt", st.session_state.current_prompt, height=340)
    with c2:
        if st.button("Generate improved prompt", type="primary"):
            proposal = prompt_change_proposal(
                current,
                charts.prepare_results(st.session_state.last_results),
                st.session_state.project.get("industry") or "regulated fintech support",
            )
            st.session_state.improved_prompt = proposal["prompt"]
            st.session_state.prompt_proposal_metadata = proposal
        improved = st.text_area("Improved system prompt", st.session_state.improved_prompt, height=340)

    st.session_state.current_prompt = current
    st.session_state.improved_prompt = improved
    if st.button("Save prompts"):
        database.save_prompt(st.session_state.project_id, "Current Prompt", current, "current")
        proposal_metadata = st.session_state.get("prompt_proposal_metadata", {})
        database.save_prompt(
            st.session_state.project_id,
            "Improved Prompt",
            improved,
            "candidate",
            explanation=proposal_metadata.get("label", "Editable candidate prompt version"),
            motivated_by_failures=proposal_metadata.get("motivated_by_failures", []),
        )
        st.success("Immutable prompt versions saved. The candidate is not promoted until it is evaluated.")


def render_eval_dataset() -> None:
    st.title("Evaluation Dataset")
    c1, c2 = st.columns([0.34, 0.66])
    with c1:
        if st.button("Load sample evaluation dataset", type="primary"):
            st.session_state.eval_df = normalize_eval_dataset(load_sample_eval_dataset())
            st.success("Sample evaluation dataset loaded.")
        uploaded = st.file_uploader("Upload evaluation dataset", type=EVALUATION_UPLOAD_TYPES)
        if uploaded is not None:
            try:
                st.session_state.eval_df = read_eval_dataset(uploaded.name, uploaded.getvalue())
                st.success("Evaluation dataset validated and loaded.")
            except Exception as exc:
                st.error(str(exc))
        df = st.session_state.eval_df
        if not df.empty:
            c1a, c1b = st.columns(2)
            c1a.metric("Questions", len(df))
            c1b.metric("Escalation cases", int(bool_series(df["should_escalate"]).sum()))
            st.bar_chart(df["category"].value_counts())
            if "expected_source" in df:
                st.bar_chart(df["expected_source"].value_counts())
            coverage = coverage_analysis(df)
            st.write("Coverage", coverage)
            quality = coverage["quality_report"]
            for error in quality["errors"]:
                st.error(error)
            for warning in quality["warnings"]:
                st.warning(warning)
            if quality["launch_eligible"]:
                st.success("Dataset meets the configured structural launch-evidence requirements.")
        schema_template = pd.DataFrame(
            [
                {
                    "case_id": "case-0001",
                    "question": "User input",
                    "category": "Policy",
                    "expected_behavior": "answer",
                    "severity": "high",
                    "tags": '["regression"]',
                    "expected_answers": '["Acceptable answer"]',
                    "expected_sources": '["Policy document"]',
                    "should_escalate": "false",
                }
            ]
        )
        st.download_button(
            "Download schema template",
            schema_template.to_csv(index=False),
            "evaluation_dataset_template.csv",
            "text/csv",
        )
    with c2:
        if st.session_state.eval_df.empty:
            st.info(
                "CSV, TSV, Excel, JSON, and JSONL are supported. Required columns: question, expected_answer, expected_source, category, should_escalate"
            )
        else:
            edited = st.data_editor(
                st.session_state.eval_df, hide_index=True, use_container_width=True, num_rows="dynamic"
            )
            errors = validate_dataset_frame(edited, allow_legacy=True)
            if errors:
                st.error(f"Dataset has {len(errors)} validation error(s).")
                st.dataframe(
                    pd.DataFrame([error.to_dict() for error in errors]), hide_index=True, use_container_width=True
                )
            elif st.button("Apply dataset edits", type="primary"):
                st.session_state.eval_df = normalize_eval_dataset(edited)
                st.success("Dataset edits validated. A new immutable snapshot will be created when the run starts.")


def render_evaluator_calibration() -> None:
    st.title("Evaluator Calibration")
    st.info(
        "Compare automatic failure labels with independent human reviews on held-out cases. Calibration metrics are "
        "descriptive observations; they do not establish statistical confidence without a separate power analysis."
    )
    threshold_configuration = EvaluatorThresholdConfiguration()
    st.caption(
        f"Evaluator {EVALUATOR_VERSION} · immutable threshold version "
        f"{threshold_configuration.version[:12]} · development rows are excluded from observed metrics."
    )

    c1, c2 = st.columns([0.34, 0.66])
    with c1:
        uploaded = st.file_uploader(
            "Upload human-reviewed calibration data",
            type=["csv", "json", "jsonl"],
            help="Required columns: case_id, split, human_labels, automatic_labels.",
        )
        if uploaded is not None:
            try:
                st.session_state.calibration_reviews_df = read_calibration_dataset(
                    uploaded.name,
                    uploaded.getvalue(),
                )
                st.success("Calibration reviews validated and loaded.")
            except Exception as exc:
                st.error(str(exc))

        schema_template = pd.DataFrame(
            [
                {
                    "case_id": "heldout-0001",
                    "split": "holdout",
                    "human_labels": '["unsupported_claim"]',
                    "automatic_labels": '["unsupported_claim"]',
                    "notes": "Independent review notes",
                }
            ]
        )
        st.download_button(
            "Download calibration template",
            schema_template.to_csv(index=False),
            "evaluator_calibration_template.csv",
            "text/csv",
        )
        selected_labels = st.multiselect(
            "Evaluator labels to calibrate",
            list(DEFAULT_CALIBRATION_LABELS),
            default=list(DEFAULT_CALIBRATION_LABELS),
        )
        requirements = CalibrationRequirements()
        st.caption(
            f"Minimum evidence per label: {requirements.minimum_reviewed_cases} held-out cases, "
            f"{requirements.minimum_positive_cases} positives, {requirements.minimum_negative_cases} negatives, "
            f"precision ≥ {requirements.minimum_precision:.0%}, recall ≥ {requirements.minimum_recall:.0%}, "
            f"false-positive rate ≤ {requirements.maximum_false_positive_rate:.0%}."
        )

    with c2:
        reviews = st.data_editor(
            st.session_state.calibration_reviews_df,
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            key="calibration_review_editor",
        )
        st.caption(
            "Use split=holdout, calibration, or test for independent review evidence. Use development for rows that "
            "must remain excluded. Labels may be JSON arrays or comma-separated values."
        )
        if st.button("Validate and save calibration result", type="primary"):
            if not selected_labels:
                st.error("Select at least one evaluator label.")
            else:
                try:
                    result = run_calibration_workflow(
                        database.get_repository(),
                        st.session_state.workspace_context,
                        reviews,
                        evaluator_version=EVALUATOR_VERSION,
                        labels=selected_labels,
                        requirements=requirements,
                        thresholds=threshold_configuration,
                    )
                except Exception as exc:
                    st.error(f"Calibration could not be saved: {exc}")
                else:
                    st.session_state.calibration_reviews_df = reviews
                    st.session_state.calibration_result = result
                    if result["status"] == "calibrated":
                        st.success("Calibration requirements are met for every selected evaluator label.")
                    else:
                        st.warning(
                            "Calibration was saved, but the evidence is insufficient for a launch verdict. "
                            "Review the per-label sample and error rates below."
                        )

    result = st.session_state.get("calibration_result")
    st.subheader("Active calibration evidence")
    if not result:
        st.warning("No qualifying held-out calibration result is attached. Launch evidence remains insufficient.")
        return
    status_label = "Calibrated" if result.get("status") == "calibrated" else "Insufficiently calibrated"
    c1, c2, c3 = st.columns(3)
    c1.metric("Status", status_label)
    c2.metric("Held-out reviews", int(result.get("reviewed_cases", 0)))
    c3.metric("Excluded development rows", int(result.get("excluded_non_holdout_cases", 0)))
    rows = []
    for label, metrics in result.get("evaluators", {}).items():
        matrix = metrics.get("confusion_matrix", {})
        rows.append(
            {
                "evaluator_label": label,
                "precision": metrics.get("precision"),
                "recall": metrics.get("recall"),
                "f1": metrics.get("f1"),
                "false_positive_rate": metrics.get("false_positive_rate"),
                "false_negative_rate": metrics.get("false_negative_rate"),
                "true_positive": matrix.get("true_positive"),
                "false_positive": matrix.get("false_positive"),
                "true_negative": matrix.get("true_negative"),
                "false_negative": matrix.get("false_negative"),
                "sample_sufficient": metrics.get("sample_sufficient"),
                "requirements_met": metrics.get("requirements_met"),
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    for limitation in result.get("limitations", []):
        st.warning(limitation)
    st.caption(str(result.get("statistical_claim") or "No statistical confidence claim is available."))
    with st.expander("Technical calibration metadata"):
        st.json(
            {
                "calibration_id": result.get("calibration_id"),
                "calibration_version": result.get("calibration_version"),
                "threshold_version": result.get("threshold_version"),
                "held_out_splits": result.get("held_out_splits", []),
                "requirements": result.get("requirements", {}),
            }
        )


def external_target_from_state() -> ExternalHTTPTarget:
    values = st.session_state.external_target_config
    configuration = ExternalTargetConfig(
        name=str(values.get("name") or "External Assistant"),
        endpoint=str(values.get("endpoint") or ""),
        method=str(values.get("method") or "POST"),
        headers=dict(values.get("headers") or {}),
        request_template=dict(values.get("request_template") or {"input": "${question}"}),
        response_mappings=dict(values.get("response_mappings") or {"answer": "$.answer"}),
        timeout_seconds=float(values.get("timeout_seconds") or 30.0),
        retry_count=int(values.get("retry_count") or 2),
        streaming=bool(values.get("streaming", False)),
        health_check_path=values.get("health_check_path") or None,
    )
    secrets = SecretResolver({"SESSION_EXTERNAL_AUTH": st.session_state.external_target_secret})
    return ExternalHTTPTarget(configuration, secrets)


def render_target_setup() -> None:
    st.title("Target Setup")
    if not external_connections_available():
        st.info(
            "External API connections are disabled on this public deployment. Use saved-answer review or your own local deployment."
        )
        return
    st.info(
        "Choose Synthetic in Run Evaluation for workflow demonstrations, Direct model for a foundation-model call, "
        "or configure an External API here to test your production assistant. External calls never fall back to mock data."
    )
    st.caption(privacy_notice())
    values = dict(st.session_state.external_target_config)
    values["name"] = st.text_input("Target name", values.get("name", "External Assistant"))
    values["endpoint"] = st.text_input(
        "HTTPS endpoint", values.get("endpoint", ""), placeholder="https://assistant.example.com/v1/chat"
    )
    values["method"] = st.selectbox(
        "HTTP method",
        ["POST", "PUT", "PATCH", "GET"],
        index=["POST", "PUT", "PATCH", "GET"].index(values.get("method", "POST")),
    )
    c1, c2, c3 = st.columns(3)
    values["timeout_seconds"] = c1.number_input(
        "Timeout seconds", 0.1, 300.0, float(values.get("timeout_seconds", 30.0))
    )
    values["retry_count"] = c2.number_input("Retries", 0, 10, int(values.get("retry_count", 2)))
    values["streaming"] = c3.checkbox("SSE streaming response", bool(values.get("streaming", False)))
    values["health_check_path"] = st.text_input("Optional health-check path", values.get("health_check_path", ""))
    header_text = st.text_area(
        "Headers JSON (use secret://SESSION_EXTERNAL_AUTH; never paste a secret here)",
        json.dumps(values.get("headers", {"Authorization": "secret://SESSION_EXTERNAL_AUTH"}), indent=2),
        height=120,
    )
    request_text = st.text_area(
        "JSON request template",
        json.dumps(values.get("request_template", {"input": "${question}", "context": "${context}"}), indent=2),
        height=150,
    )
    mapping_text = st.text_area(
        "Response JSON-path mappings",
        json.dumps(
            values.get(
                "response_mappings",
                {
                    "answer": "$.answer",
                    "citations": "$.citations",
                    "escalation": "$.escalation",
                    "tool_calls": "$.tool_calls",
                },
            ),
            indent=2,
        ),
        height=150,
    )
    st.session_state.external_target_secret = st.text_input(
        "Session-only authentication secret",
        value=st.session_state.external_target_secret,
        type="password",
        help="Resolved at request time. It is never included in the stored target version.",
    )
    if st.button("Validate and save target configuration", type="primary"):
        try:
            values["headers"] = json.loads(header_text)
            values["request_template"] = json.loads(request_text)
            values["response_mappings"] = json.loads(mapping_text)
            st.session_state.external_target_config = values
            adapter = external_target_from_state()
            st.success(f"Target configuration valid. Version {adapter.version[:12]}. No raw secret will be stored.")
        except Exception as exc:
            st.error(str(exc))
    allow_health_check = False
    if values.get("endpoint"):
        allow_health_check = st.checkbox(
            "I authorize a test request to this endpoint and any charges on my connected account."
        )
    if values.get("endpoint") and st.button("Run health check / test request", disabled=not allow_health_check):
        try:
            st.session_state.external_target_config = {
                **values,
                "headers": json.loads(header_text),
                "request_template": json.loads(request_text),
                "response_mappings": json.loads(mapping_text),
            }
            response = external_target_from_state().health_check()
            if response.status.value == "passed":
                st.success(f"Health check passed (HTTP {response.http_status or 'not returned'}).")
            else:
                st.error(response.safe_error or "Health check failed.")
        except Exception as exc:
            st.error(str(exc))


def render_run_evaluation(*, live_only: bool = False) -> None:
    st.title("Run Evaluation")
    ready = (
        bool(st.session_state.chunks) and not st.session_state.eval_df.empty and bool(st.session_state.current_prompt)
    )
    if not st.session_state.chunks:
        st.warning("Load documents before running evaluation.")
    if st.session_state.eval_df.empty:
        st.warning("Load an evaluation dataset before running evaluation.")

    target_options = (
        ["External assistant/API", "Direct foundation model"]
        if live_only
        else ["Synthetic demonstration", "Direct foundation model", "External assistant/API"]
    )
    target_kind = st.radio(
        "Evaluation target",
        target_options,
        index=1 if live_only and not external_connections_available() else 0,
        horizontal=True,
    )
    with st.expander("Prompt comparison (optional)"):
        mode = st.radio(
            "Evaluation mode", ["Current Prompt Only", "Current Prompt vs Improved Prompt"], horizontal=True
        )
    target_adapter = None
    mock_scenario = "__per_case__"
    if target_kind == "Synthetic demonstration":
        model = "mock-model"
        synthetic_scenarios = {
            "Use each dataset row's scenario": "__per_case__",
            "Success / grounded answer": "correct_grounded_answer",
            "Hallucination / unsupported answer": "hallucination",
            "Safe refusal": "refusal",
            "Correct escalation": "escalation",
            "Contradiction": "contradiction",
            "Citation failure": "citation_failure",
            "Missed escalation": "missed_escalation",
            "Timeout": "timeout",
            "Malformed response": "malformed_response",
            "Rate limiting": "rate_limiting",
            "Privacy leakage": "privacy_leakage",
            "Retrieval failure": "retrieval_failure",
        }
        selected_scenario = st.selectbox(
            "Synthetic scenario",
            list(synthetic_scenarios),
            help="Per-case mode uses the versioned mock_scenario field from each dataset row.",
        )
        mock_scenario = synthetic_scenarios[selected_scenario]
        st.warning("Synthetic demonstration — not model-quality evidence. This run cannot receive a launch verdict.")
        st.info(
            "Synthetic responses are deterministic and ignore prompt content. Prompt comparisons are shown only as "
            "workflow demonstrations and cannot establish that one prompt is better."
        )
    elif target_kind == "Direct foundation model":
        direct_models = [item for item in model_options() if item != "mock-model"]
        if not direct_models:
            st.error(f"No {st.session_state.api_provider} key is configured. Add your session key in Settings.")
            model = config.PROVIDER_MODELS[selected_provider()][0]
            ready = False
        else:
            model = st.selectbox("Exact model identifier", direct_models)
            st.success(
                f"Direct {st.session_state.api_provider} execution via {api_key_source()}. Provider failures remain failures."
            )
    else:
        model = "external-assistant"
        if not external_connections_available():
            st.info(
                "External API connections are disabled on this public deployment. Choose a provider model with your own key, or review saved answers."
            )
            ready = False
        else:
            try:
                target_adapter = external_target_from_state()
                st.success(f"External target configured. Version {target_adapter.version[:12]}.")
            except Exception as exc:
                st.error(f"Configure the external target on Target Setup before running: {exc}")
                ready = False

    with st.expander("Advanced run settings"):
        c1, c2, c3, c4 = st.columns(4)
        top_k = c1.slider("top_k retrieval", 1, 8, config.DEFAULT_TOP_K)
        similarity_threshold = c2.slider(
            "Minimum similarity",
            0.0,
            1.0,
            float(st.session_state.similarity_threshold),
            0.01,
        )
        latency_threshold = c3.number_input(
            "Latency gate (ms)", min_value=100, value=config.LATENCY_THRESHOLD_MS, step=100
        )
        cost_threshold = c4.number_input(
            "Cost gate (USD)", min_value=0.0, value=config.COST_THRESHOLD_USD, step=0.005, format="%.3f"
        )
        c1, c2 = st.columns(2)
        max_concurrency = c1.slider("Concurrency", 1, 16, 4)
        max_retries = c2.slider("Retryable-error retries", 0, 5, 2)
        candidate_tuned_on_dataset = st.checkbox(
            "A candidate in this run was tuned using cases from this dataset",
            help="If selected, the dataset must contain an explicit tuning_disclosure before it can support a launch verdict.",
        )

    prompts = {"Current Prompt": st.session_state.current_prompt}
    if mode == "Current Prompt vs Improved Prompt":
        prompts["Improved Prompt"] = st.session_state.improved_prompt

    calls = len(st.session_state.eval_df) * len(prompts)
    st.info(
        f"Preflight: {st.session_state.eval_df['case_id'].nunique() if 'case_id' in st.session_state.eval_df else len(st.session_state.eval_df)} "
        f"unique cases · {calls} total executions · {len(prompts)} candidate(s). "
        f"Provider cost is {'$0 synthetic' if model == 'mock-model' else 'unknown until exact token usage is returned'}."
    )
    run_dataset_quality = dataset_quality_report(
        st.session_state.eval_df,
        available_sources={str(chunk.get("source_name") or "") for chunk in st.session_state.chunks},
        candidate_tuned_on_dataset=candidate_tuned_on_dataset,
    )
    if not run_dataset_quality["launch_eligible"]:
        st.warning(
            "This run may be useful for diagnosis, but its dataset cannot support a launch verdict. "
            + " ".join(run_dataset_quality["errors"] + run_dataset_quality["warnings"])
        )
    confirmed = (
        st.checkbox(
            "I authorize sending these questions and sources to the selected target, and any charges on my connected account."
        )
        if model != "mock-model"
        else st.checkbox("I understand this run uses fictional answers to demonstrate the workflow.")
    )
    if st.button("Run Evaluation", type="primary", disabled=not (ready and confirmed)):
        progress = st.progress(0)
        status = st.empty()

        def update_progress(done: int, total: int) -> None:
            progress.progress(done / total)
            status.write(f"Completed {done} of {total} executions.")

        evaluation_frame = st.session_state.eval_df.copy()
        if model == "mock-model" and mock_scenario != "__per_case__":
            evaluation_frame["mock_scenario"] = mock_scenario
        try:
            with st.spinner("Running reliability evaluation with checkpoints and explicit error states..."):
                results = run_evaluation(
                    eval_df=evaluation_frame,
                    chunks=st.session_state.chunks,
                    prompts=prompts,
                    model_name=model,
                    top_k=top_k,
                    similarity_threshold=similarity_threshold,
                    latency_threshold_ms=latency_threshold,
                    cost_threshold_usd=cost_threshold,
                    mode=mode,
                    project_id=st.session_state.project_id,
                    progress_callback=update_progress,
                    api_key=effective_api_key() if target_kind == "Direct foundation model" else None,
                    target_adapter=target_adapter,
                    max_concurrency=max_concurrency,
                    max_retries=max_retries,
                    candidate_tuned_on_dataset=candidate_tuned_on_dataset,
                    threshold_configuration=EvaluatorThresholdConfiguration(),
                    calibration_result=st.session_state.get("calibration_result"),
                )
        except Exception as exc:
            st.error(f"Run could not start safely: {exc}")
            return
        st.session_state.last_results = charts.prepare_results(results)
        st.session_state.last_top_k = top_k
        st.session_state.similarity_threshold = similarity_threshold
        st.success(execution_summary(results)["message"])
        st.dataframe(st.session_state.last_results.head(20), use_container_width=True, hide_index=True)


def render_results_dashboard() -> None:
    st.title("Results Dashboard")
    df = charts.prepare_results(st.session_state.last_results)
    if df.empty:
        st.info("Run an evaluation to populate the dashboard.")
        return
    run_counts = execution_summary(df)
    candidate_results = evaluate_candidates(df)
    st.subheader("Run-level execution summary")
    st.caption(
        "These are portfolio/run counts across all candidates. Quality and launch metrics are intentionally shown only "
        "inside each candidate card below."
    )
    c = st.columns(5)
    c[0].metric("Unique test cases", run_counts["unique_test_cases"])
    c[1].metric("Total executions", run_counts["total_executions"])
    c[2].metric("Quality-scored", run_counts["quality_scored_executions"])
    c[3].metric("Infrastructure errors", run_counts["infrastructure_errors"])
    c[4].metric("Candidates", len(candidate_results))
    c = st.columns(5)
    c[0].metric("Quality passes", run_counts["quality_passes"])
    c[1].metric("Quality failures", run_counts["quality_failures"])
    c[2].metric("Retries", run_counts["retries"])
    c[3].metric("Skipped", run_counts["skipped_executions"])
    c[4].metric("Cancelled", run_counts["cancelled_executions"])

    st.subheader("Candidate-specific quality and launch gates")
    for candidate, evaluation in candidate_results.items():
        identity = evaluation.get("candidate", {})
        with st.expander(f"{evaluation['verdict']} · {candidate}", expanded=True):
            st.caption(
                f"Prompt: {identity.get('prompt_name', 'Unnamed')} · "
                f"Target: {identity.get('target_name', 'Unknown')} ({identity.get('target_type', 'unknown')}) · "
                f"Model: {identity.get('model_name', 'Unknown')} · Version: {identity.get('short_version', 'unknown')}"
            )
            if evaluation.get("evidence_notice"):
                st.warning(evaluation["evidence_notice"])
            metrics = evaluation.get("metrics", {})
            counts = evaluation.get("counts", {})
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(
                "Overall quality",
                f"{float(metrics['overall_quality']) * 100:.1f}%" if "overall_quality" in metrics else "N/A",
            )
            c2.metric(
                "Groundedness",
                f"{float(metrics['groundedness']) * 100:.1f}%" if "groundedness" in metrics else "N/A",
            )
            c3.metric(
                "Citation support",
                f"{float(metrics['citation_support']) * 100:.1f}%" if "citation_support" in metrics else "N/A",
            )
            c4.metric(
                "Escalation accuracy",
                f"{float(metrics['escalation_accuracy']) * 100:.1f}%" if "escalation_accuracy" in metrics else "N/A",
            )
            st.caption(
                f"{counts.get('unique_test_cases', 0)} unique cases · "
                f"{counts.get('total_executions', 0)} executions · "
                f"{counts.get('quality_scored_executions', 0)} quality-scored · "
                f"{counts.get('execution_error_count', 0)} infrastructure errors"
            )
            st.dataframe(pd.DataFrame(evaluation["gate_results"]), hide_index=True, use_container_width=True)
            for warning in evaluation.get("warnings", []):
                st.warning(warning)
            technical_key = safe_display_text(identity.get("candidate_id") or candidate)
            if st.checkbox("Show technical identifiers", key=f"candidate_technical_{technical_key}"):
                st.caption("Full immutable identifiers are retained for reproduction and report verification.")
                for label, key in [
                    ("Candidate ID", "candidate_id"),
                    ("Prompt version", "prompt_version"),
                    ("Target version", "target_version"),
                ]:
                    if identity.get(key):
                        st.markdown(f"**{label}**")
                        st.code(str(identity[key]), language="text")
    st.info(charts.insight_summary(df, top_k=st.session_state.last_top_k))

    st.subheader("Run-level diagnostics across candidates")
    st.caption(
        "The charts below describe the selected run portfolio and must not be interpreted as a combined candidate launch score."
    )
    c1, c2 = st.columns(2)
    c1.plotly_chart(charts.prompt_comparison_chart(df), use_container_width=True)
    c2.plotly_chart(charts.category_score_chart(df), use_container_width=True)
    c1, c2 = st.columns(2)
    c1.plotly_chart(charts.failure_distribution_chart(df), use_container_width=True)
    c2.plotly_chart(charts.hallucination_distribution_chart(df), use_container_width=True)
    c1, c2 = st.columns(2)
    c1.plotly_chart(charts.latency_chart(df), use_container_width=True)
    c2.plotly_chart(charts.cost_chart(df), use_container_width=True)

    st.subheader("Quality failures")
    quality_failures = df[(df.get("execution_status", "passed") == "passed") & (df["failure_type"] != "Passed")]
    cols = [
        column
        for column in [
            "case_id",
            "question",
            "category",
            "severity",
            "actual_answer",
            "overall_score",
            "hallucination_risk",
            "failure_type",
            "failure_labels",
            "suggested_fix",
        ]
        if column in df
    ]
    st.dataframe(safe_dataframe(quality_failures[cols]), hide_index=True, use_container_width=True)
    infrastructure = df[df.get("execution_status", "passed") != "passed"]
    if not infrastructure.empty:
        st.subheader("Execution errors (excluded from quality averages)")
        error_columns = [
            column
            for column in [
                "case_id",
                "question",
                "execution_status",
                "error_code",
                "safe_error",
                "model_name",
                "target_type",
            ]
            if column in infrastructure
        ]
        st.dataframe(safe_dataframe(infrastructure[error_columns]), hide_index=True, use_container_width=True)


def render_failure_analysis() -> None:
    st.title("Failure Analysis")
    df = charts.prepare_results(st.session_state.last_results)
    if df.empty:
        st.info("Run an evaluation to inspect failures.")
        return
    infrastructure = df[df.get("execution_status", pd.Series(["passed"] * len(df), index=df.index)) != "passed"]
    if not infrastructure.empty:
        st.subheader("Execution errors")
        error_columns = [
            column
            for column in [
                "case_id",
                "question",
                "execution_status",
                "error_code",
                "safe_error",
                "prompt_name",
                "model_name",
                "target_type",
            ]
            if column in infrastructure
        ]
        st.dataframe(safe_dataframe(infrastructure[error_columns]), hide_index=True, use_container_width=True)
    quality = df[df.get("execution_status", pd.Series(["passed"] * len(df), index=df.index)) == "passed"]
    show_passed = st.checkbox("Include passed quality cases", False)
    if not show_passed:
        quality = quality[quality["failure_type"] != "Passed"]
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    category = c1.multiselect(
        "Category", sorted(quality["category"].dropna().unique()), default=sorted(quality["category"].dropna().unique())
    )
    failure = c2.multiselect(
        "Root cause",
        sorted(quality["failure_type"].dropna().unique()),
        default=sorted(quality["failure_type"].dropna().unique()),
    )
    risk = c3.multiselect(
        "Risk",
        sorted(quality["hallucination_risk"].dropna().unique()),
        default=sorted(quality["hallucination_risk"].dropna().unique()),
    )
    prompt = c4.multiselect(
        "Prompt",
        sorted(quality["prompt_name"].dropna().unique()),
        default=sorted(quality["prompt_name"].dropna().unique()),
    )
    model = c5.multiselect(
        "Model",
        sorted(quality["model_name"].dropna().unique()),
        default=sorted(quality["model_name"].dropna().unique()),
    )
    severities = sorted(quality["severity"].dropna().unique()) if "severity" in quality else []
    severity = c6.multiselect("Severity", severities, default=severities)
    filtered = quality[
        quality["category"].isin(category)
        & quality["failure_type"].isin(failure)
        & quality["hallucination_risk"].isin(risk)
        & quality["prompt_name"].isin(prompt)
        & quality["model_name"].isin(model)
    ]
    if "severity" in filtered:
        filtered = filtered[filtered["severity"].isin(severity)]
    table_cols = [
        "question",
        "category",
        "expected_answer",
        "actual_answer",
        "expected_source",
        "retrieved_sources_display",
        "should_escalate",
        "actual_escalation",
        "overall_score",
        "hallucination_risk",
        "failure_type",
        "failure_labels",
        "evaluator_confidence",
        "suggested_fix",
        "prompt_name",
        "model_name",
    ]
    table_cols = [column for column in table_cols if column in filtered]
    st.dataframe(safe_dataframe(filtered[table_cols]), hide_index=True, use_container_width=True)
    st.download_button(
        "Export filtered failures as CSV",
        csv_report(filtered, redact_personal_data=True),
        "ai_reliability_failures.csv",
        "text/csv",
    )

    page_size = st.select_slider("Cases per page", options=[10, 25, 50, 100], value=25)
    page_count = max(1, (len(filtered) + page_size - 1) // page_size)
    page = st.number_input("Page", min_value=1, max_value=page_count, value=1)
    page_rows = filtered.iloc[(int(page) - 1) * page_size : int(page) * page_size]
    st.caption(f"Showing {len(page_rows)} of {len(filtered)} filtered cases. No failures are silently truncated.")
    for position, (_, row) in enumerate(page_rows.iterrows()):
        detail = failure_presentation(row.to_dict())
        with st.expander(f"{detail['root_cause']} | {safe_display_text(row.get('question'))}"):
            st.markdown(f"**Summary:** {detail['summary']}")
            st.markdown(f"**Root cause:** {detail['root_cause']}")
            st.markdown(f"**Why this case failed:** {detail['why_failed']}")
            c1, c2 = st.columns(2)
            c1.markdown("**Expected behavior**")
            c1.write(detail["expected_behavior"])
            c2.markdown("**Actual behavior**")
            c2.write(detail["actual_behavior"])
            st.markdown("**Relevant source passages**")
            if detail["source_passages"]:
                for passage in detail["source_passages"]:
                    similarity = passage.get("similarity")
                    similarity_label = f" · similarity {similarity:.2f}" if similarity is not None else ""
                    st.caption(f"{passage['document']} · {passage['location']}{similarity_label}")
                    render_plain_text(passage["passage"])
            else:
                st.caption("No supporting passage was recorded for this execution.")
            confidence = detail["confidence"]
            st.markdown(
                "**Evaluator confidence:** "
                + (f"{confidence * 100:.0f}%" if confidence is not None else "Not recorded")
            )
            for limitation in detail["limitations"]:
                st.warning(limitation)
            st.markdown(f"**Recommended next action:** {detail['recommended_action']}")
            metric_columns = [
                "expected_answer_match_score",
                "source_retrieval_score",
                "citation_correctness_score",
                "groundedness_score",
                "escalation_correctness_score",
                "overall_score",
            ]
            metric_rows = [
                {"metric": column, "score": row.get(column)} for column in metric_columns if column in row.index
            ]
            if metric_rows:
                st.dataframe(pd.DataFrame(metric_rows), hide_index=True, use_container_width=True)
            case_key = f"{int(page)}_{position}_{row.get('case_id', 'unknown')}_{row.get('prompt_name', 'unknown')}"
            if st.checkbox("Show raw evaluator output", key=f"raw_failure_{case_key}"):
                st.json(detail["raw_evaluator_output"])
            if st.checkbox("Show final prompt and technical metadata", key=f"technical_failure_{case_key}"):
                st.code(detail["final_prompt"], language="text")
                st.json(detail["technical_metadata"])


def render_prompt_comparison() -> None:
    st.title("Prompt Comparison")
    df = charts.prepare_results(st.session_state.last_results)
    if df.empty or df["prompt_name"].nunique() < 2:
        st.info("Run Current Prompt vs Improved Prompt mode to view prompt comparison.")
        return
    if "target_type" in df and set(df["target_type"].dropna().astype(str)) == {"synthetic_mock"}:
        st.warning(
            "Synthetic prompt comparison is not a model-quality comparison. Deterministic scenarios ignore prompt "
            "content, so neither prompt can be declared better from this run."
        )
        st.dataframe(charts.prompt_metric_table(df), hide_index=True, use_container_width=True)
        st.info(charts.insight_summary(df, top_k=st.session_state.last_top_k))
        return
    table = charts.prompt_metric_table(df)
    st.dataframe(table, hide_index=True, use_container_width=True)
    st.plotly_chart(charts.prompt_comparison_chart(df), use_container_width=True)
    st.info(charts.insight_summary(df, top_k=st.session_state.last_top_k))
    if df["model_name"].nunique() > 1:
        st.subheader("Model comparison")
        st.plotly_chart(charts.model_comparison_chart(df), use_container_width=True)
    else:
        st.caption("Model comparison is hidden because only one model was evaluated.")


def render_run_history() -> None:
    st.title("Run History / Comparison")
    runs = database.eval_runs_df()
    if runs.empty:
        st.info("No historical runs are available in this workspace.")
        return
    st.dataframe(runs, hide_index=True, use_container_width=True)
    labels = {f"#{int(row['id'])} · {row['run_name']} · {row['status']}": int(row["id"]) for _, row in runs.iterrows()}
    baseline_label = st.selectbox("Baseline run", list(labels), index=min(1, len(labels) - 1))
    candidate_label = st.selectbox("Candidate run", list(labels), index=0)
    if st.button("Compare selected runs", type="primary"):
        baseline = charts.prepare_results(
            pd.DataFrame(
                database.get_repository().list_results(st.session_state.workspace_context, labels[baseline_label])
            )
        )
        candidate = charts.prepare_results(
            pd.DataFrame(
                database.get_repository().list_results(st.session_state.workspace_context, labels[candidate_label])
            )
        )
        comparison = compare_candidates(baseline, candidate)
        st.session_state.last_results = candidate
        if comparison["regressed"]:
            st.error("Candidate regressed or failed a launch gate.")
        else:
            st.success("No material regression was detected under the configured comparison rules.")
        for limitation in comparison.get("limitations", []):
            st.warning(limitation)
        c1, c2 = st.columns(2)
        c1.metric("Observed quality delta", f"{comparison['quality_delta'] * 100:+.1f} pp")
        c2.metric("Regressions", len(comparison["regressions"]))

        st.subheader("Candidate summaries")
        columns = st.columns(2)
        for column, side in zip(columns, ["baseline", "candidate"], strict=False):
            column.markdown(f"**{side.title()} run**")
            summaries = comparison["candidate_summaries"][side]
            if not summaries:
                column.info("No candidate evidence is available.")
            for name, evaluation in summaries.items():
                column.markdown(f"{evaluation['verdict']} · {name}")
                counts = evaluation.get("counts", {})
                column.caption(
                    f"{counts.get('unique_test_cases', 0)} unique cases · "
                    f"{counts.get('quality_scored_executions', 0)} quality-scored · "
                    f"{counts.get('execution_error_count', 0)} infrastructure errors"
                )

        st.subheader("Metric deltas")
        metric_delta_rows = [
            {
                "metric": metric,
                "baseline": values["baseline"],
                "candidate": values["candidate"],
                "delta": values["delta"],
            }
            for metric, values in comparison["metric_deltas"].items()
        ]
        st.dataframe(pd.DataFrame(metric_delta_rows), hide_index=True, use_container_width=True)

        st.subheader("Launch-gate changes")
        if comparison["gate_changes"]:
            st.dataframe(pd.DataFrame(comparison["gate_changes"]), hide_index=True, use_container_width=True)
        else:
            st.caption("No launch-gate state or explanation changed.")

        c1, c2 = st.columns(2)
        c1.markdown("**New failures**")
        if comparison["new_failures"]:
            c1.dataframe(pd.DataFrame(comparison["new_failures"]), hide_index=True, use_container_width=True)
        else:
            c1.caption("No newly introduced failures.")
        c2.markdown("**Resolved failures**")
        if comparison["resolved_failures"]:
            c2.dataframe(pd.DataFrame(comparison["resolved_failures"]), hide_index=True, use_container_width=True)
        else:
            c2.caption("No resolved failures.")

        st.subheader("Failure regressions by severity and category")
        c1, c2 = st.columns(2)
        severity_rows = comparison["failure_count_deltas"]["severity"]
        category_rows = comparison["failure_count_deltas"]["category"]
        c1.dataframe(pd.DataFrame(severity_rows), hide_index=True, use_container_width=True)
        c2.dataframe(pd.DataFrame(category_rows), hide_index=True, use_container_width=True)

        st.subheader("Infrastructure, cost, and latency")
        operational_rows = []
        for side in ["baseline", "candidate"]:
            operational_rows.append(
                {
                    "run": side,
                    "infrastructure_errors": comparison["infrastructure"][side]["count"],
                    "infrastructure_error_rate": comparison["infrastructure"][side]["rate"],
                    **comparison["cost_latency"][side],
                }
            )
        st.dataframe(pd.DataFrame(operational_rows), hide_index=True, use_container_width=True)

        st.subheader("Dataset and immutable version differences")
        version_rows = []
        for side in ["baseline", "candidate"]:
            for kind, values in comparison["versions"][side].items():
                version_rows.append({"run": side, "version_type": kind, "values": ", ".join(values)})
        if version_rows:
            st.dataframe(pd.DataFrame(version_rows), hide_index=True, use_container_width=True)
        else:
            st.caption("No version identifiers were recorded for these runs.")
        raw_comparison = json.dumps(safe_nested(comparison), ensure_ascii=False, indent=2, default=str)
        st.download_button(
            "Download raw comparison JSON",
            raw_comparison,
            "ai_reliability_run_comparison.json",
            "application/json",
        )


def render_settings_export() -> None:
    st.title("Settings / Export")
    st.subheader("Model provider and API key")
    st.caption(
        "In-app keys are stored only in Streamlit session state. They are not saved to SQLite and are not written to files."
    )
    provider_label = st.selectbox(
        "Provider",
        list(PROVIDER_LABELS),
        index=list(PROVIDER_LABELS).index(st.session_state.get("api_provider", "OpenAI")),
    )
    st.session_state.api_provider = provider_label
    provider = selected_provider()
    secret_name = PROVIDER_SECRET_NAMES[provider]
    st.caption(
        "Only the API key you enter in this browser session can be used in the public app."
        if public_session_mode()
        else f"Key priority: in-app key > Streamlit secrets > .env {secret_name}. Missing credentials produce an explicit error; synthetic mode must be selected separately."
    )
    keys = dict(st.session_state.get("provider_api_keys", {}))
    entered_key = st.text_input(
        f"{provider_label} API key",
        value=keys.get(provider, ""),
        type="password",
        placeholder="Paste the provider API key",
        help="This key is used only when you authorize a provider call. It stays in this browser session."
        if public_session_mode()
        else f"Priority: in-app key > Streamlit secrets > .env {secret_name}. There is no automatic mock fallback.",
    )
    keys[provider] = entered_key.strip()
    st.session_state.provider_api_keys = keys
    c1, c2, c3 = st.columns(3)
    c1.metric("Effective API key", api_key_status_label())
    c2.metric("Key source", api_key_source())
    c3.metric("Real LLM Mode", "Available" if effective_api_key() else "Unavailable")
    if keys.get(provider):
        if st.button("Clear in-app API key"):
            keys[provider] = ""
            st.session_state.provider_api_keys = keys
            st.success("In-app API key cleared from this session.")
            st.rerun()
    if not effective_api_key():
        st.info(
            "Direct foundation-model execution is unavailable until a key is configured. "
            "The separately selected synthetic target remains demonstration-only."
        )
    st.divider()

    c1, c2, c3 = st.columns(3)
    provider_models = config.PROVIDER_MODELS[provider]
    c1.metric("Streamlit secrets key", "Present" if streamlit_secret_api_key(provider) else "Not present")
    c2.metric(
        "Server credentials",
        "Disabled for public sessions"
        if public_session_mode()
        else ("Present" if config.api_key_for_provider(provider) else "Not present"),
    )
    c3.metric("Model A", provider_models[0])
    st.metric("Model B", provider_models[1] if len(provider_models) > 1 else "Not configured")
    storage_label = (
        "PostgreSQL production storage"
        if str(config.DATABASE_URL).lower().startswith(("postgresql://", "postgres://"))
        else "Local SQLite development storage"
    )
    st.metric("Storage mode", storage_label)
    st.caption("Local filesystem and connection locations are intentionally hidden from the user interface.")
    if st.session_state.get("public_session_notice"):
        st.info(st.session_state.public_session_notice)

    runs = database.eval_runs_df()
    if not runs.empty:
        st.subheader("Run history")
        st.dataframe(runs, hide_index=True, use_container_width=True)
    all_results = charts.prepare_results(database.all_results_df())
    if not all_results.empty:
        redact_exports = st.checkbox("Redact detected PII in exports", value=True)
        export_source = (
            charts.prepare_results(st.session_state.last_results)
            if not st.session_state.last_results.empty
            else all_results
        )
        selected_run_ids = export_source.get("run_id", pd.Series(dtype=int)).dropna().unique().tolist()
        export_run_id = int(selected_run_ids[0]) if len(selected_run_ids) == 1 else None
        csv_data = csv_report(export_source, redact_personal_data=redact_exports)
        json_data = json_report(export_source, redact_personal_data=redact_exports)
        html_data = html_report(export_source, redact_personal_data=redact_exports)
        c1, c2, c3 = st.columns(3)
        c1.download_button(
            "Download CSV report",
            csv_data,
            "ai_reliability_results.csv",
            "text/csv",
            on_click=audited_export,
            args=("csv", csv_data, export_run_id),
        )
        c2.download_button(
            "Download JSON report",
            json_data,
            "ai_reliability_results.json",
            "application/json",
            on_click=audited_export,
            args=("json", json_data, export_run_id),
        )
        c3.download_button(
            "Download HTML report",
            html_data,
            "ai_reliability_results.html",
            "text/html",
            on_click=audited_export,
            args=("html", html_data, export_run_id),
        )
    st.subheader("Destructive actions")
    confirmation = st.text_input("Type DELETE WORKSPACE DATA to enable destructive actions")
    c1, c2 = st.columns(2)
    if c1.button("Clear this workspace's evaluation results", disabled=confirmation != "DELETE WORKSPACE DATA"):
        database.clear_results(confirm=True)
        st.session_state.last_results = pd.DataFrame()
        st.success("Evaluation results for the active workspace were deleted. Other workspaces were not touched.")
    if c2.button("Reset all data in this workspace", disabled=confirmation != "DELETE WORKSPACE DATA"):
        database.reset_current_workspace(confirm=True)
        start_custom_mode()
        st.success(
            "Active workspace data was deleted. The operation is recorded in the audit log and does not affect other workspaces."
        )


def main() -> None:
    apply_theme()
    init_state()
    st.sidebar.title("AI Reliability Studio")
    st.sidebar.caption("Sources → answers → reviewed findings")
    pages = {
        "Overview": render_overview,
        "Review saved answers": render_saved_answers,
        "Evaluate live assistant": render_live_assistant,
        "Project Setup": render_project_setup,
        "Knowledge Base": render_knowledge_base,
        "System Prompt": render_system_prompt,
        "Target Setup": render_target_setup,
        "Evaluation Dataset": render_eval_dataset,
        "Evaluator Calibration": render_evaluator_calibration,
        "Run Evaluation": render_run_evaluation,
        "Results Dashboard": render_results_dashboard,
        "Failure Analysis": render_failure_analysis,
        "Prompt Comparison": render_prompt_comparison,
        "Run History / Comparison": render_run_history,
        "Settings / Export": render_settings_export,
    }
    requested = st.session_state.pop("_next_page", None)
    if requested in pages:
        st.session_state.page = requested
    with st.sidebar.expander("All tools and settings", expanded=False):
        page = st.radio("Navigate", list(pages), key="page")
        st.caption(
            f"{len(st.session_state.chunks)} source passages · {len(st.session_state.eval_df)} evaluation questions"
        )
    if st.session_state.get("public_session_notice"):
        st.sidebar.info(st.session_state.public_session_notice)
        if st.sidebar.button("End session and clear my data"):
            end_public_session(st.session_state)
            st.rerun()
    if page != "Overview" and st.button("← Start", key="return_to_start"):
        navigate_to("Overview")
    if message := st.session_state.pop("_workflow_message", None):
        st.success(message)
    if warning := st.session_state.pop("_workflow_warning", None):
        st.warning(warning)
    pages[page]()


if __name__ == "__main__":
    main()
