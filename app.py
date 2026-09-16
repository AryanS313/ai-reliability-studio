from __future__ import annotations

import hashlib
import html
import json
import os
import sqlite3
import sys
import time
import uuid
from copy import deepcopy
from pathlib import Path

import pandas as pd
import streamlit as st

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
from src.domain import ROLE_RANK, Role
from src.evaluator import EVALUATION_UPLOAD_TYPES, normalize_eval_dataset, read_eval_dataset, run_evaluation
from src.hosted_limits import (
    HOSTED_MAX_CONCURRENCY,
    HOSTED_MAX_EXECUTIONS,
    HOSTED_MAX_RETRIES,
    HOSTED_MAX_TIMEOUT_SECONDS,
    HostedLimitError,
    run_limit_notice,
)
from src.presentation import (
    candidate_title,
    execution_summary,
    failure_presentation,
    metric_display,
    metric_label,
    readiness_check_rows,
    safe_display_text,
    safe_nested,
    version_difference_rows,
)
from src.product_analytics import record_event
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
from src.security import AuthorizationError, privacy_notice, validate_upload_batch
from src.suggestions import generate_improved_prompt, prompt_change_proposal
from src.targets import ExternalHTTPTarget, ExternalTargetConfig, SecretResolver, target_configuration_for_storage
from src.ui_display import display_value, field_label, readable_frame, review_labels
from src.ui_workflows import (
    REVIEW_LABELS,
    evaluate_review_workspace,
    new_review_workspace,
    optional_review_text,
    read_reference_uploads,
    read_review_workspace,
    replacement_batch,
    sample_replacements,
    sample_review_workspace,
    save_case_review,
    source_extraction_warnings,
    starter_pack,
    utc_now_text,
)
from src.vector_store import SimpleVectorStore
from src.versioning import version_hash

st.set_page_config(page_title="AI Reliability Studio", page_icon="ARS", layout="wide")

PROVIDER_LABELS = {"OpenAI": "openai", "Google Gemini": "gemini", "Anthropic Claude": "anthropic"}
TARGET_LABELS = {
    "External assistant/API": "My existing assistant",
    "Direct foundation model": "A model with my documents",
}
PROVIDER_SECRET_NAMES = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


def apply_theme() -> None:
    st.markdown(
        """
    <style>
      :root { --ars-text: #182c3b; --ars-muted: #475569; }

      .block-container { max-width: 1240px; padding-top: 2.5rem; padding-bottom: 4rem; }

      h1, h2, h3 { letter-spacing: -.025em; }
      h1 { font-size: 2.25rem !important; }
      .hero { border-left: 4px solid #087f75; padding: .25rem 0 .25rem 1.4rem; margin-bottom: 1.5rem; }
      .hero h1 { margin: 0 0 .4rem; }
      .hero p { max-width: 760px; line-height: 1.65; }
      .eyebrow { color: #0c625d; font-size: .8rem; font-weight: 700; letter-spacing: .09em; text-transform: uppercase; }
      [data-testid="stMetric"] { border: 1px solid #aebdcd; border-radius: 12px; padding: .8rem; }

      [data-testid="stMetricValue"] { font-size: 1.8rem; }
      button, input, textarea, select { font-size: 1rem; }
      button:focus-visible, input:focus-visible, textarea:focus-visible,
      [role="radio"]:focus-visible, [role="combobox"]:focus-visible {
        outline: 3px solid #087f75 !important; outline-offset: 3px !important;
      }
      @media(max-width: 768px) {
        .block-container { padding: 1rem .9rem 3rem; }
        h1 { font-size: 1.8rem !important; }
        [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
        [data-testid="stColumn"] { flex: 1 1 100% !important; width: 100% !important; min-width: 0 !important; }
      }
      @media(prefers-reduced-motion: reduce) { * { scroll-behavior: auto !important; } }
    </style>
    """,
        unsafe_allow_html=True,
    )


def init_state() -> None:
    session = bind_current_session()
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
    st.session_state.workspace_context = authenticated_context
    if "calibration_result" not in st.session_state:
        threshold_version = EvaluatorThresholdConfiguration().version
        latest_calibration = database.get_repository().latest_calibration(
            authenticated_context,
            threshold_version=threshold_version,
        )
        st.session_state.calibration_result = (
            latest_calibration.get("result") if latest_calibration is not None else None
        )
    st.session_state.setdefault("project", {"name": "", "use_case": "Support assistant", "notes": ""})
    st.session_state.setdefault("documents", [])
    st.session_state.setdefault("chunks", [])
    st.session_state.setdefault("eval_df", pd.DataFrame())
    st.session_state.setdefault(
        "calibration_reviews_df",
        pd.DataFrame(columns=["case_id", "split", "human_labels", "automatic_labels", "notes"]),
    )
    st.session_state.setdefault("current_prompt", prompts["Current Prompt"])
    st.session_state.setdefault("improved_prompt", prompts["Improved Prompt"])
    st.session_state.setdefault("last_results", pd.DataFrame())
    st.session_state.setdefault("last_top_k", config.DEFAULT_TOP_K)
    st.session_state.setdefault("similarity_threshold", config.DEFAULT_SIMILARITY_THRESHOLD)
    st.session_state.setdefault("external_target_config", {})
    st.session_state.setdefault("external_target_secret", "")
    st.session_state.setdefault("privacy_acknowledged", False)
    st.session_state.setdefault("offline_workspace", None)
    st.session_state.setdefault("offline_baseline", pd.DataFrame())
    st.session_state.setdefault("offline_candidate", pd.DataFrame())
    st.session_state.setdefault("navigation", "Start")
    st.session_state.setdefault("advanced_tool", "Choose a tool")
    st.session_state.setdefault("prepare_step", "1 · Project")
    st.session_state.setdefault("target_kind", "Synthetic demonstration")
    if "analytics_session" not in st.session_state:
        st.session_state.analytics_session = uuid.uuid4().hex
        st.session_state.session_started_at = time.monotonic()
        track("session_started", mode=config.APP_ACCESS_MODE)


def load_demo() -> None:
    st.session_state.pop("imported_connection_draft", None)
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
    if config.APP_ACCESS_MODE == "public-demo":
        return ""
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
        return "No API key"
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
    configured = os.getenv("STREAMLIT_SECRETS_FILE", "").strip()
    candidates = [
        Path(configured).expanduser() if configured else None,
        config.ROOT_DIR / ".streamlit" / "secrets.toml",
        Path.home() / ".streamlit" / "secrets.toml",
    ]
    return any(path is not None and path.is_file() for path in candidates)


def start_custom_mode() -> None:
    st.session_state.pop("imported_connection_draft", None)
    st.session_state.pop("project_restore_notice", None)
    st.session_state.pop("_show_project_restore", None)
    st.session_state.mode = "Custom Upload Mode"
    st.session_state.calibration_result = None
    st.session_state.external_target_config = {}
    st.session_state.external_target_secret = ""
    st.session_state.loaded_dataset_upload = None
    st.session_state.target_kind = (
        "Direct foundation model" if config.is_browser_runtime() else "External assistant/API"
    )
    st.session_state.project = {
        "name": "",
        "company": "",
        "industry": "",
        "use_case": "",
        "notes": "",
    }
    st.session_state.project_id = None
    st.session_state.documents = []
    st.session_state.chunks = []
    st.session_state.eval_df = pd.DataFrame()
    st.session_state.current_prompt = (
        "You are a customer support assistant. Answer only from the supplied source evidence. "
        "Cite the source and relevant passage. Preserve dates, quantities, conditions and exceptions. "
        "If evidence is missing or conflicting, say what is unknown and escalate to the appropriate team. "
        "Do not authorize transactions, change accounts or disclose personal data."
    )
    st.session_state.improved_prompt = generate_improved_prompt(st.session_state.current_prompt)
    st.session_state.last_results = pd.DataFrame()


def save_uploaded_documents(files) -> int:
    if not custom_access(require_project=True):
        return 0
    try:
        validate_upload_batch(len(files))
    except ValueError as exc:
        st.error(safe_display_text(exc))
        return 0
    documents = []
    existing = database.documents_df(project_id=st.session_state.project_id)
    hashes = set(existing.get("content_hash", pd.Series(dtype=str)).tolist())
    for uploaded in files:
        try:
            document = load_uploaded_document(uploaded)
            if document.get("content_hash") in hashes:
                st.info(f"{safe_display_text(uploaded.name)} is already indexed; duplicate skipped.")
                continue
            hashes.add(document.get("content_hash"))
            documents.append(document)
            for warning in document.get("warnings", []):
                st.warning(safe_display_text(warning))
        except Exception as exc:
            st.warning(f"{safe_display_text(uploaded.name)} skipped: {safe_display_text(exc)}")
            track("workflow_error", stage="documents", outcome="failure")
    if documents:
        duplicates = detect_duplicate_documents(documents)
        for duplicate in duplicates:
            st.warning(
                f"Possible duplicate: {safe_display_text(duplicate['document'])}. Review before using it as evidence."
            )
        database.save_documents_and_chunks(
            documents, chunk_documents(documents), project_id=st.session_state.project_id
        )
        st.session_state.chunks = database.load_chunks(project_id=st.session_state.project_id)
        st.session_state.documents = database.documents_df(project_id=st.session_state.project_id).to_dict("records")
        track("document_ingested", document_count=len(documents), chunk_count=len(st.session_state.chunks))
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


def track(name: str, **properties) -> None:
    if st.session_state.get("project_id") is not None:
        properties.setdefault("project_id", int(st.session_state.project_id))
    record_event(
        database.get_repository(),
        st.session_state.workspace_context,
        name,
        st.session_state.analytics_session,
        **properties,
    )


def navigate(page: str, step: str | None = None) -> None:
    st.session_state.pending_navigation = page
    st.session_state.pending_tool_reset = True
    if step:
        st.session_state.pending_prepare_step = step
    # Callbacks already run before the next render; rerun only during a render.


def acknowledge_privacy() -> None:
    st.session_state.privacy_acknowledged = bool(st.session_state.privacy_acknowledgement_control)


def hosted_upload_options(max_bytes: int | None = None) -> dict[str, int]:
    """Match native upload affordances to validators without newer browser API calls."""
    if not config.hosted_sessions_enabled():
        return {}
    limit = min(config.MAX_UPLOAD_BYTES, 2 * 1024 * 1024) if max_bytes is None else max_bytes
    # Streamlit accepts whole MiB; validators retain the exact byte limit.
    return {"max_upload_size": max(1, (limit + 1024 * 1024 - 1) // (1024 * 1024))}


def custom_access(*, require_project: bool = True, minimum_role: Role = Role.EDITOR) -> bool:
    if config.APP_ACCESS_MODE == "public-demo":
        st.info("This demonstration accepts fictional sample data only. Custom evaluation is unavailable here.")
        return False
    if ROLE_RANK[st.session_state.workspace_context.role] < ROLE_RANK[minimum_role]:
        st.info(
            f"Your role can review and export results. This workflow requires the {minimum_role.value} role or higher."
        )
        return False
    if not st.session_state.privacy_acknowledged:
        if config.hosted_sessions_enabled():
            st.info(
                "This website processes your uploads and evaluations on its server in an isolated, temporary session. "
                "Your provider key stays in session memory. Download your project before leaving; a session end, "
                "inactivity timeout or server restart can clear your work."
            )
        st.info(
            "Use data you are authorized to evaluate. Sources, prompts and results are stored in this workspace. "
            "Real calls send the selected inputs to your target. Automated redaction is incomplete; remove sensitive data before uploading."
        )
        st.checkbox(
            "I have reviewed the data handling notice and will use approved, non-sensitive test data.",
            key="privacy_acknowledgement_control",
            on_change=acknowledge_privacy,
        )
        return False
    if require_project and st.session_state.project_id is None:
        st.info("Create or reopen a project first so every source, case and run has a release history.")
        st.button("Go to project setup", on_click=navigate, args=("Prepare", "1 · Project"))
        return False
    return True


def save_dataset_snapshot() -> None:
    repository = database.get_repository()
    repository.create_dataset_version(
        st.session_state.workspace_context,
        st.session_state.project_id,
        "Evaluation cases",
        st.session_state.eval_df.to_dict("records"),
        immutable=True,
    )
    track("dataset_saved", case_count=len(st.session_state.eval_df))


def restore_project(project: dict) -> None:
    start_custom_mode()
    project_id = int(project["id"])
    st.session_state.project = project
    st.session_state.project_id = project_id
    st.session_state.documents = database.documents_df(project_id=project_id).to_dict("records")
    st.session_state.chunks = database.load_chunks(project_id=project_id)
    prompts = database.prompts_df(project_id=project_id)
    for kind, key in [("current", "current_prompt"), ("candidate", "improved_prompt")]:
        if not prompts.empty:
            matching = prompts[prompts["prompt_type"].eq(kind)]
            if not matching.empty:
                st.session_state[key] = str(matching.iloc[0]["prompt_text"])
    assets = database.get_repository().load_project_configuration(st.session_state.workspace_context, project_id)
    if assets.get("dataset_records"):
        st.session_state.eval_df = normalize_eval_dataset(pd.DataFrame(assets["dataset_records"]))
    st.session_state.external_target_config = assets.get("external_target_config") or {}
    runs = project_runs()
    if not runs.empty:
        st.session_state.last_results = charts.prepare_results(
            pd.DataFrame(
                database.get_repository().list_results(st.session_state.workspace_context, int(runs.iloc[0]["id"]))
            )
        )
    track("project_reopened")


def project_runs() -> pd.DataFrame:
    runs = database.eval_runs_df()
    if runs.empty or st.session_state.project_id is None:
        return pd.DataFrame()
    return runs[runs["project_id"].eq(st.session_state.project_id)].copy()


def render_project_transfer(location: str) -> None:
    if config.APP_ACCESS_MODE == "public-demo":
        return
    if st.session_state.project_id is not None and st.session_state.privacy_acknowledged:
        from src.project_workspace import export_project_workspace

        st.caption(
            "Download your project to keep its source passages, questions, saved instructions and review history. "
            "Credentials are excluded. Treat the download as private data."
        )
        try:
            content = export_project_workspace(
                database.get_repository(), st.session_state.workspace_context, st.session_state.project_id
            )
            st.download_button(
                "Download project to resume later",
                content,
                "reliability-project.json",
                "application/json",
                key=f"project_download_{location}",
            )
        except (ValueError, AuthorizationError) as exc:
            st.error(f"The project could not be downloaded: {safe_display_text(exc)}")
    if st.button("Resume a project", key=f"project_resume_{location}"):
        st.session_state._show_project_restore = True
    if not st.session_state.get("_show_project_restore"):
        return
    with st.container(border=True):
        st.subheader("Resume a downloaded project")
        if not custom_access(require_project=False):
            return
        st.caption(
            "Restore a project download from this app. It creates a separate project and keeps your current work. "
            "Enter credentials again before connecting. Imported history is not independently verified execution evidence."
        )
        saved = st.file_uploader(
            "Project download",
            type=["json"],
            key=f"project_restore_upload_{location}",
            **hosted_upload_options(20 * 1024 * 1024),
        )
        if st.button("Restore project", disabled=saved is None, key=f"project_restore_{location}"):
            from src.project_workspace import restore_project_workspace

            try:
                repository = database.get_repository()
                context = st.session_state.workspace_context
                restored_id = restore_project_workspace(repository, context, saved.getvalue())
                project = next(item for item in repository.list_projects(context) if int(item["id"]) == restored_id)
                restore_project(project)
                st.session_state.provider_api_keys = dict.fromkeys(PROVIDER_LABELS.values(), "")
                st.session_state.openai_api_key = ""
                for key in list(st.session_state):
                    if str(key).startswith(("provider_secret_", "_provider_key_input_")):
                        del st.session_state[key]
                st.session_state.pop("_show_project_restore", None)
                st.session_state.project_restore_notice = (
                    "Project restored. Imported history is not independently verified execution evidence. "
                    "Re-enter credentials and run a fresh evaluation when you are ready."
                )
                navigate("History" if not project_runs().empty else "Prepare", "2 · Sources")
                st.rerun()
            except (ValueError, TypeError, AuthorizationError) as exc:
                st.error(f"The project could not be restored: {safe_display_text(exc)}")


def render_progress() -> None:
    checks = [
        ("Project", st.session_state.project_id is not None),
        ("Sources", bool(st.session_state.chunks)),
        ("Cases", not st.session_state.eval_df.empty),
        ("Prompt", bool(st.session_state.current_prompt.strip())),
        ("Results", not st.session_state.last_results.empty),
    ]
    complete = sum(done for _, done in checks)
    st.progress(complete / len(checks), text=f"{complete} of {len(checks)} review steps ready")
    st.caption(" · ".join(f"{'✓' if done else '○'} {name}" for name, done in checks))


def run_sample_review() -> None:
    if st.session_state.mode == "Demo Mode" and not st.session_state.last_results.empty:
        navigate("Review")
        st.rerun()
    started = time.monotonic()
    load_demo()
    track("sample_loaded", document_count=len(st.session_state.documents), case_count=len(st.session_state.eval_df))
    track("run_started", target_type="synthetic_mock", synthetic=True, execution_count=len(st.session_state.eval_df))
    with st.spinner("Checking 32 fictional cases against sample policies…"):
        results = run_evaluation(
            eval_df=st.session_state.eval_df,
            chunks=st.session_state.chunks,
            prompts={"Current Prompt": st.session_state.current_prompt},
            model_name="mock-model",
            top_k=config.DEFAULT_TOP_K,
            similarity_threshold=config.DEFAULT_SIMILARITY_THRESHOLD,
            latency_threshold_ms=config.LATENCY_THRESHOLD_MS,
            cost_threshold_usd=config.COST_THRESHOLD_USD,
            project_id=st.session_state.project_id,
            mode="Sample review",
            max_concurrency=(
                1 if config.is_browser_runtime() else HOSTED_MAX_CONCURRENCY if config.hosted_sessions_enabled() else 4
            ),
            max_retries=0,
            calibration_result=None,
        )
    st.session_state.last_results = charts.prepare_results(results)
    counts = execution_summary(results)
    track(
        "run_completed",
        target_type="synthetic_mock",
        synthetic=True,
        execution_count=len(results),
        scored_count=counts["quality_scored_executions"],
        error_count=counts["infrastructure_errors"],
        duration_ms=(time.monotonic() - started) * 1000,
        outcome="partial" if counts["infrastructure_errors"] else "success",
    )
    st.session_state.sample_duration_ms = (time.monotonic() - started) * 1000
    navigate("Review")
    st.rerun()


def render_prepare() -> None:
    render_progress()
    step = st.radio(
        "Preparation step",
        ["1 · Project", "2 · Sources", "3 · Cases", "4 · Prompt"],
        key="prepare_step",
        horizontal=True,
    )
    {
        "1 · Project": render_project_setup,
        "2 · Sources": render_knowledge_base,
        "3 · Cases": render_eval_dataset,
        "4 · Prompt": render_system_prompt,
    }[step]()
    if st.session_state.project_id and step != "1 · Project":
        steps = {"2 · Sources": ("3 · Cases", "Continue to cases"), "3 · Cases": ("4 · Prompt", "Continue to prompt")}
        if step in steps:
            next_step, label = steps[step]
            st.button(label, on_click=navigate, args=("Prepare", next_step))
        else:
            st.button("Connect an assistant", on_click=navigate, args=("Connect",))


def render_provider_settings() -> None:
    st.subheader("Model provider")
    if not custom_access(require_project=True):
        return
    st.write("Choose the company that will generate answers using your documents and instructions.")
    provider_label = st.selectbox(
        "Provider",
        list(PROVIDER_LABELS),
        index=list(PROVIDER_LABELS).index(st.session_state.api_provider),
        key="_provider_choice",
    )
    st.session_state.api_provider = provider_label
    provider = selected_provider()
    key_name = f"provider_secret_{provider}"
    key_value = st.text_input(
        f"{provider_label} API key",
        type="password",
        key=key_name,
        value=st.session_state.provider_api_keys.get(provider, ""),
        help=(
            "An API key is a private access code from your model-provider account. "
            "Keep it private like a password. The provider may charge your account for generated answers."
        ),
    )
    keys = dict(st.session_state.provider_api_keys)
    keys[provider] = key_value.strip()
    st.session_state.provider_api_keys = keys
    st.caption(
        "The key you enter stays only in this open session. It is excluded from project downloads, events and reports. "
        "Enter it again in a new session."
    )
    st.caption(f"Key source: {api_key_source()}.")
    if effective_api_key():
        st.success("A key is configured. Its validity will be checked by the first provider request.")
    else:
        st.info("Add your provider key before running. Missing or rejected credentials remain execution errors.")

    def clear_key():
        st.session_state[key_name] = ""
        st.session_state.provider_api_keys[provider] = ""

    st.button("Clear session key", on_click=clear_key, disabled=not bool(key_value))


def render_overview() -> None:
    st.markdown(
        """<div class="hero"><p class="eyebrow">Design-partner beta · Support assistants</p>
    <h1>Know what to fix before your next AI release.</h1>
    <p>Check your support assistant against your policies and expected answers. Find unsupported claims,
    missed exceptions and unsafe handoffs, then compare the next revision with the same cases.</p></div>""",
        unsafe_allow_html=True,
    )
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.subheader("See a release review")
            st.write("Run 32 fictional support cases. Inspect a failure, its source evidence and the next action.")
            st.caption("No account, API key or external call. Synthetic evidence cannot validate an assistant.")
            if st.button(
                "Try the sample review",
                type="primary",
                use_container_width=True,
                disabled=st.session_state.workspace_context.role in {Role.VIEWER, Role.REVIEWER},
            ):
                run_sample_review()
    with right:
        with st.container(border=True):
            st.subheader("Evaluate your assistant")
            st.write(
                "Bring approved source documents, expected-answer cases and a staging assistant endpoint or provider key."
            )
            if config.APP_ACCESS_MODE == "public-demo":
                st.caption("This demonstration uses fictional samples only. Custom evaluation is unavailable here.")
            elif st.button("Start a project", use_container_width=True):
                start_custom_mode()
                navigate("Prepare", "1 · Project")
                st.rerun()
    if st.session_state.project_id:
        st.divider()
        st.subheader("Continue your release review")
        render_progress()
        if st.button("Continue this project"):
            navigate("Review" if not st.session_state.last_results.empty else "Prepare")
            st.rerun()
    st.caption(
        "Automated findings need source review. A gate summarizes configured checks; it is not launch certification. "
        "Real release evidence also requires representative cases and held-out human calibration."
    )
    render_project_transfer("start")

    with st.expander("Review answers you already have"):
        st.write(
            "Review saved assistant answers against their sources, record a decision and compare replacements. No provider connection is needed."
        )
        if st.button("Try a saved-answer example", key="start_saved_sample"):
            load_demo()
            install_review_workspace(sample_review_workspace())
            navigate_to("Review saved answers")
        if config.APP_ACCESS_MODE != "public-demo":
            if st.button("Review saved answers", key="start_saved"):
                navigate_to("Review saved answers")
            if st.button("Resume a review", key="start_resume"):
                st.session_state._show_resume_workspace = True
                navigate_to("Review saved answers")
            if st.button("Evaluate live assistant", key="start_live"):
                navigate_to("Evaluate live assistant")


def render_project_setup() -> None:
    st.title("Prepare a release review")
    if not custom_access(require_project=False, minimum_role=Role.VIEWER):
        return
    workspace = st.session_state.workspace_context
    can_edit = ROLE_RANK[workspace.role] >= ROLE_RANK[Role.EDITOR]
    projects = database.get_repository().list_projects(workspace)
    if projects:
        labels = {f"{item['name']} · #{item['id']}": item for item in projects}
        selected = st.selectbox("Reopen a saved project", ["Choose a project", *labels])
        if selected in labels and st.button("Reopen project"):
            restore_project(labels[selected])
            if can_edit:
                navigate("Prepare", "2 · Sources")
            else:
                navigate("Review")
            st.rerun()
    if st.session_state.project_id:
        st.success(f"Project saved: {safe_display_text(st.session_state.project.get('name'))}")
        if can_edit:
            st.button("Continue to sources", on_click=navigate, args=("Prepare", "2 · Sources"))
        else:
            st.button("Open saved review", on_click=navigate, args=("Review",))
        return
    if not custom_access(require_project=False):
        return
    with st.form("create_project"):
        name = st.text_input("Project name", placeholder="e.g. Support assistant · September release", max_chars=120)
        use_case = st.text_input(
            "What does the assistant help with?", value="Answer customer questions from support policies", max_chars=300
        )
        submitted = st.form_submit_button("Create project", type="primary")
    if submitted:
        if not name.strip():
            st.error("Enter a project name so your sources and release history stay together.")
            return
        project = {"name": name.strip(), "use_case": use_case.strip(), "industry": "Support", "notes": ""}
        st.session_state.project_id = database.save_project(project)
        st.session_state.project = project
        st.session_state.mode = "Custom Upload Mode"
        track("project_created")
        st.success("Project created. Next, add the sources your assistant should follow.")
        st.button("Continue to sources", on_click=navigate, args=("Prepare", "2 · Sources"))


def render_knowledge_base() -> None:
    st.title("Knowledge Base")
    if not custom_access(require_project=True):
        return
    c1, c2 = st.columns([0.38, 0.62])
    with c1:
        if st.button("Load sample documents", type="primary"):
            documents, chunks = load_sample_documents()
            st.session_state.documents = documents
            st.session_state.chunks = chunks
            database.save_documents_and_chunks(documents, chunks, project_id=st.session_state.project_id)
            st.session_state.chunks = database.load_chunks(project_id=st.session_state.project_id)
            st.session_state.documents = database.documents_df(project_id=st.session_state.project_id).to_dict(
                "records"
            )
            st.success(f"Loaded {len(documents)} documents and {len(chunks)} source passages.")
        uploaded = st.file_uploader(
            "Upload knowledge-base documents",
            type=UPLOAD_TYPES,
            accept_multiple_files=True,
            help="Supports text, Markdown, PDF, DOCX, RTF, CSV/TSV, Excel, JSON/JSONL, HTML, XML/YAML, and PPTX.",
            **hosted_upload_options(),
        )
        if config.hosted_sessions_enabled():
            st.caption(
                f"Up to {min(config.MAX_DOCUMENTS_PER_UPLOAD, 8)} files per upload, "
                f"{min(config.MAX_UPLOAD_BYTES, 2 * 1024 * 1024) / 1024 / 1024:g} MB per file. "
                "Only upload approved, non-sensitive test documents."
            )
        st.info(privacy_notice())
        st.caption(
            "Legacy .doc and image-only/scanned documents are not supported; convert them to DOCX or searchable PDF first."
        )
        if uploaded and st.button("Index uploaded documents"):
            loaded_count = save_uploaded_documents(uploaded)
            if loaded_count:
                st.success(f"Added {loaded_count} documents. {len(st.session_state.chunks)} source passages are ready.")
        docs_df = database.documents_df(project_id=st.session_state.project_id)
        st.metric("Source passages", len(st.session_state.chunks))
        if not docs_df.empty:
            columns = [
                column
                for column in ["filename", "source_name", "file_type", "chunk_count", "extraction_status"]
                if column in docs_df
            ]
            st.dataframe(readable_frame(docs_df[columns]), hide_index=True, use_container_width=True)
    with c2:
        st.subheader("Retrieval test")
        question = st.text_input("Sample question", "What does the policy say about my request?")
        top_k = st.slider("Passages to find", 1, 8, config.DEFAULT_TOP_K, key="kb_top_k")
        threshold = st.slider(
            "Minimum hybrid similarity",
            0.0,
            1.0,
            float(st.session_state.similarity_threshold),
            0.01,
            key="kb_similarity_threshold",
        )
        if st.button("Test retrieval", disabled=not st.session_state.chunks):
            store = SimpleVectorStore()
            store.build(st.session_state.chunks)
            results = store.retrieve(question, top_k=top_k, similarity_threshold=threshold)
            st.caption(
                "Passages are matched by meaning and wording."
                if store.embedder.semantic
                else "Studio's search matches wording and related terms. It does not measure your assistant's own search quality."
            )
            if not results:
                st.info("No passages matched. Try a more specific question or lower the similarity threshold.")
            for chunk in results:
                with st.expander(f"{chunk['source_name']} | similarity {chunk['similarity']:.2f}"):
                    render_plain_text(chunk["chunk_text"])
        st.subheader("Source passage preview")
        preview = pd.DataFrame(st.session_state.chunks[:10])
        if not preview.empty:
            preview_columns = [
                column for column in ["source_name", "page", "section", "chunk_text"] if column in preview
            ]
            st.dataframe(readable_frame(preview[preview_columns]), hide_index=True, use_container_width=True)


def render_system_prompt() -> None:
    st.title("System Prompt")
    if not custom_access(require_project=True):
        return
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Load sample current prompt"):
            st.session_state.current_prompt = default_prompts()["Current Prompt"]
        current = st.text_area("Current system prompt", st.session_state.current_prompt, height=340)
    with c2:
        if st.button("Draft candidate prompt", type="primary"):
            proposal = prompt_change_proposal(
                current,
                charts.prepare_results(st.session_state.last_results),
                st.session_state.project.get("industry") or "customer support",
            )
            st.session_state.improved_prompt = proposal["prompt"]
            st.session_state.prompt_proposal_metadata = proposal
        st.caption("Editable template proposal. Improvement must be established by a real comparison.")
        improved = st.text_area("Candidate system prompt", st.session_state.improved_prompt, height=340)

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
        st.success(
            "Instructions saved. Earlier versions are kept automatically. Test the candidate before choosing it for a release."
        )


def render_eval_dataset() -> None:
    from src.case_editor import FIELD_LABELS, RISK_LABELS, case_editor_frame, coverage_findings, merge_case_edits

    st.title("Test questions")
    if not custom_access(require_project=True):
        return
    st.caption("Describe what your users ask, the answer you expect and the source that supports it.")
    if st.session_state.eval_df.empty and st.button("Create cases in the editor"):
        st.session_state.eval_df = pd.DataFrame(
            [
                {
                    "case_id": "case-" + uuid.uuid4().hex[:16],
                    "question": "",
                    "expected_answer": "",
                    "expected_source": "",
                    "category": "Policy",
                    "should_escalate": False,
                    "severity": "high",
                }
            ]
        )
    c1, c2 = st.columns([0.34, 0.66])
    with c1:
        if st.button("Load sample evaluation dataset", type="primary"):
            st.session_state.eval_df = normalize_eval_dataset(load_sample_eval_dataset())
            save_dataset_snapshot()
            st.success("Sample questions loaded and saved to this project.")
        uploaded = st.file_uploader(
            "Upload evaluation dataset",
            type=EVALUATION_UPLOAD_TYPES,
            help="Upload a CSV or spreadsheet of questions. Existing JSON question files also work.",
            **hosted_upload_options(),
        )
        if config.hosted_sessions_enabled():
            st.caption(
                f"Question files may contain up to {min(config.MAX_DATASET_ROWS, 500)} questions. "
                f"Each review can generate at most {HOSTED_MAX_EXECUTIONS} answers, including instruction comparisons."
            )
        upload_digest = hashlib.sha256(uploaded.getvalue()).hexdigest() if uploaded is not None else None
        if uploaded is not None and upload_digest != st.session_state.get("loaded_dataset_upload"):
            try:
                st.session_state.eval_df = read_eval_dataset(uploaded.name, uploaded.getvalue())
                st.session_state.loaded_dataset_upload = upload_digest
                save_dataset_snapshot()
                st.success("Questions checked and saved to this project.")
            except Exception:
                st.error(
                    "The question file could not be loaded. Check the required columns and values against the template below."
                )
        df = st.session_state.eval_df
        if not df.empty:
            c1a, c1b = st.columns(2)
            c1a.metric("Questions", len(df))
            c1b.metric(
                "Human handoffs", int(bool_series(df.get("should_escalate", pd.Series(False, index=df.index))).sum())
            )
            if not validate_dataset_frame(df, allow_legacy=True):
                coverage = coverage_analysis(df)
                coverage["quality_report"] = dataset_quality_report(
                    df, available_sources={str(chunk.get("source_name") or "") for chunk in st.session_state.chunks}
                )
                quality = coverage["quality_report"]
                st.caption(
                    f"{len(coverage['categories'])} question groups · {quality['critical_case_count']} critical-impact questions"
                )
                if any(count < 5 for count in coverage["categories"].values()):
                    st.warning(
                        "Some question groups have fewer than 5 questions. Add examples for a more representative review."
                    )
                if quality["launch_eligible"]:
                    st.success(
                        "The question-set checks passed. Confirm that these questions represent your users and risks."
                    )
                else:
                    st.info(
                        "You can try an evaluation with these questions. More coverage or case details are needed before they can support a release decision."
                    )
                with st.expander("What these questions cover"):
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "Question group": str(group).replace("-", " ").replace("_", " ").capitalize(),
                                    "Questions": count,
                                }
                                for group, count in coverage["categories"].items()
                            ]
                        ),
                        hide_index=True,
                        use_container_width=True,
                    )
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {"Impact of a wrong answer": str(level).capitalize(), "Questions": count}
                                for level, count in coverage["severities"].items()
                            ]
                        ),
                        hide_index=True,
                        use_container_width=True,
                    )
                    missing = quality.get("missing_categories", [])
                    if missing:
                        st.markdown("**Risk areas still to cover**")
                        for risk in missing:
                            st.write("• " + RISK_LABELS.get(risk, str(risk).replace("-", " ").capitalize()))
                    for finding in coverage_findings(coverage):
                        st.write("• " + finding)
                    st.caption("Coverage describes your question set. It does not establish assistant quality.")
            else:
                st.info("Finish the required details in the editor to check this question set.")
        question_template = pd.DataFrame(
            [
                {
                    "question": "When should a refund dispute be handed to a person?",
                    "expected_answer": "Hand the dispute to the support team for review.",
                    "expected_source": "Refund policy",
                    "category": "Human handoff",
                    "should_escalate": True,
                    "severity": "high",
                }
            ]
        )
        st.download_button(
            "Download question template",
            question_template.to_csv(index=False),
            "evaluation_questions_template.csv",
            "text/csv",
        )
    with c2:
        if st.session_state.eval_df.empty:
            st.info(
                "Start with the template or add your first question in the editor. Include an expected answer, source, question group and whether a person should take over."
            )
            return
        st.subheader("Edit your questions")
        st.caption(
            "Edit a cell to change it. Use the last row to add a question; select a row to delete it. Editing a main answer or source keeps any saved alternatives and evaluation rules."
        )
        editor_key = (
            f"case_editor_{st.session_state.project_id}_{version_hash(st.session_state.eval_df.to_dict('records'))}"
        )
        edited = st.data_editor(
            case_editor_frame(st.session_state.eval_df),
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            key=editor_key,
            disabled=["case_id"],
            column_config={
                "case_id": None,
                "question": st.column_config.TextColumn("Question", width="large", required=True),
                "expected_answer": st.column_config.TextColumn(
                    "Main expected answer",
                    width="large",
                    help="The main answer you expect. Additional acceptable answers from your file stay saved.",
                ),
                "expected_source": st.column_config.TextColumn(
                    "Main source",
                    help="Use the document's source name. Enter Missing evidence when no supporting source should exist.",
                ),
                "category": st.column_config.TextColumn(
                    "Question group",
                    required=True,
                    default="Policy",
                    help="For example: Refunds, Human handoff or Missing information.",
                ),
                "handoff": st.column_config.SelectboxColumn(
                    "Human handoff?",
                    options=["Yes", "No", "Not specified"],
                    default="No",
                    required=True,
                    help="Should a person take over this question? Keep Not specified if the expected behavior is unknown.",
                ),
                "severity": st.column_config.SelectboxColumn(
                    "Impact",
                    options=["Low", "Medium", "High", "Critical"],
                    default="High",
                    required=True,
                    help="How serious would a wrong answer be? Critical means the greatest potential harm.",
                ),
            },
        )
        merged = None
        errors = []
        try:
            merged = merge_case_edits(st.session_state.eval_df, edited)
            errors = validate_dataset_frame(merged, allow_legacy=True)
        except ValueError as exc:
            st.error(safe_display_text(exc))
        if errors:
            st.warning("Complete or correct these details before saving:")
            rows = []
            for error in errors[:20]:
                field = FIELD_LABELS.get(error.field, "Saved case details")
                problem = (
                    "Add a value."
                    if error.code in {"blank", "missing_column"}
                    else "Use Yes, No or Not specified."
                    if error.code == "invalid_boolean"
                    else "Choose one of the listed options."
                    if error.code == "invalid_enum"
                    else "Check this value against the question template."
                )
                rows.append(
                    {
                        "Question": max(1, error.row - 1) if error.row else "Question set",
                        "Detail": field,
                        "What to fix": problem,
                    }
                )
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            if len(errors) > 20:
                st.caption(f"Showing 20 of {len(errors)} details to fix.")
        if st.button("Apply dataset edits", type="primary", disabled=merged is None or bool(errors)):
            st.session_state.eval_df = normalize_eval_dataset(merged)
            save_dataset_snapshot()
            st.success("Questions saved. Previous versions remain in the project history.")


def render_evaluator_calibration() -> None:
    st.title("Evaluator Calibration")
    if not custom_access(require_project=True, minimum_role=Role.REVIEWER):
        return
    st.info(
        "Compare automatic failure labels with independent human reviews on held-out cases. Calibration metrics are "
        "descriptive observations; they do not establish statistical confidence without a separate power analysis."
    )
    threshold_configuration = EvaluatorThresholdConfiguration()
    st.caption(
        "The evaluation rules are saved automatically. Practice cases are excluded from independent review results."
    )

    c1, c2 = st.columns([0.34, 0.66])
    with c1:
        uploaded = st.file_uploader(
            "Upload human-reviewed calibration data",
            type=["csv", "json", "jsonl"],
            help="Use the review template to match each independent human review with the automated findings for the same question.",
            **hosted_upload_options(),
        )
        if uploaded is not None:
            try:
                st.session_state.calibration_reviews_df = read_calibration_dataset(
                    uploaded.name,
                    uploaded.getvalue(),
                )
                st.success("Calibration reviews validated and loaded.")
            except Exception as exc:
                st.error(safe_display_text(exc))

        schema_template = pd.DataFrame(
            [
                {
                    "case_id": "heldout-0001",
                    "split": "holdout",
                    "human_labels": "unsupported_claim",
                    "automatic_labels": "unsupported_claim",
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
            format_func=field_label,
        )
        requirements = CalibrationRequirements()
        st.caption(
            f"Each finding type needs at least {requirements.minimum_reviewed_cases} independently reviewed questions: {requirements.minimum_positive_cases} with that problem and {requirements.minimum_negative_cases} without it."
        )
        with st.expander("Required agreement with reviewers"):
            st.write(
                f"At least {requirements.minimum_precision:.0%} of automated flags must be confirmed by reviewers."
            )
            st.write(f"At least {requirements.minimum_recall:.0%} of reviewer-confirmed problems must be detected.")
            st.write(
                f"No more than {requirements.maximum_false_positive_rate:.0%} of clean cases may be incorrectly flagged."
            )

    with c2:
        review_choices = st.session_state.calibration_reviews_df.copy()
        for column in ["human_labels", "automatic_labels"]:
            review_choices[column] = review_choices[column].map(review_labels)
        label_options = sorted(
            set(DEFAULT_CALIBRATION_LABELS)
            | {
                label
                for column in ["human_labels", "automatic_labels"]
                for labels in review_choices[column]
                for label in labels
            }
        )
        has_choice_cells = hasattr(st.column_config, "MultiselectColumn")
        split_names = {
            "holdout": "Independent review",
            "calibration": "Independent calibration",
            "test": "Independent test",
            "development": "Practice only",
            "train": "Training only",
        }
        if not has_choice_cells:
            for column in ["human_labels", "automatic_labels"]:
                review_choices[column] = review_choices[column].map(
                    lambda labels: ", ".join(field_label(label) for label in labels)
                )
            review_choices["split"] = review_choices["split"].map(lambda value: split_names.get(value, value))
            st.caption(
                "Separate finding names with commas. For example: Correctness, Groundedness. Use the same names listed in the finding selector."
            )

        def finding_column(label):
            if has_choice_cells:
                return st.column_config.MultiselectColumn(label, options=label_options, format_func=field_label)
            return st.column_config.TextColumn(label)

        reviews = st.data_editor(
            review_choices,
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            key="calibration_review_editor",
            disabled=["case_id"],
            column_config={
                "case_id": None,
                "split": st.column_config.SelectboxColumn(
                    "Use these reviews for",
                    options=list(split_names) if has_choice_cells else list(split_names.values()),
                    default="holdout" if has_choice_cells else "Independent review",
                    **({"format_func": lambda value: split_names.get(value, value)} if has_choice_cells else {}),
                ),
                "human_labels": finding_column("Human findings"),
                "automatic_labels": finding_column("Automated findings"),
                "notes": st.column_config.TextColumn("Review notes"),
            },
        )
        st.caption(
            "Choose the findings for each review. Independent reviews count toward agreement checks; practice and training rows are excluded. Reference numbers are kept automatically."
        )
        if st.button("Validate and save calibration result", type="primary"):
            reviews = reviews.copy()
            if not has_choice_cells:
                labels_by_title = {field_label(label): label for label in label_options}
                for column in ["human_labels", "automatic_labels"]:
                    reviews[column] = reviews[column].map(
                        lambda value: [
                            labels_by_title.get(item.strip(), item.strip())
                            for item in str(value).split(",")
                            if item.strip()
                        ]
                    )
                reviews["split"] = reviews["split"].map(
                    lambda value: {v: k for k, v in split_names.items()}.get(value, value)
                )
            reviews["case_id"] = reviews["case_id"].map(
                lambda value: value if pd.notna(value) and str(value).strip() else "review-" + uuid.uuid4().hex
            )
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

    if st.session_state.get("calibration_result") and st.button("Detach calibration for diagnostic runs"):
        st.session_state.calibration_result = None
        st.info("Calibration detached. New runs remain insufficiently calibrated until new held-out evidence is saved.")
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
    st.dataframe(readable_frame(pd.DataFrame(rows)), hide_index=True, use_container_width=True)
    for limitation in result.get("limitations", []):
        st.warning(limitation)
    st.caption(str(result.get("statistical_claim") or "No statistical confidence claim is available."))
    with st.expander("How these human reviews are used"):
        st.write("Only independently reviewed cases count. Practice and development cases are excluded.")
        st.write("The review history and evaluation rules are saved so that later releases can be compared fairly.")
        st.caption(
            "Changing the evaluation rules requires new evidence that the automated findings agree with human reviewers."
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
        retry_count=int(values.get("retry_count", 0)),
        streaming=bool(values.get("streaming", False)),
        health_check_path=values.get("health_check_path") or None,
    )
    secrets = SecretResolver({"SESSION_EXTERNAL_AUTH": st.session_state.external_target_secret})
    return ExternalHTTPTarget(configuration, secrets)


def render_target_setup() -> None:
    if config.is_browser_runtime():
        st.title("Connect a model provider")
        st.info(
            "This browser edition can call a model provider with your key. To review your deployed assistant here, import its saved answers."
        )
        render_provider_settings()
        st.button(
            "Review saved answers", on_click=lambda: st.session_state.update({"_next_page": "Review saved answers"})
        )
        return
    st.title("Connect your assistant")
    if not custom_access(require_project=True):
        return
    kind = st.radio(
        "What are you testing?",
        ["External assistant/API", "Direct foundation model"],
        index=0 if st.session_state.target_kind != "Direct foundation model" else 1,
        format_func=lambda value: TARGET_LABELS.get(value, value),
        key="connection_choice",
    )
    st.session_state.target_kind = kind
    if kind == "Direct foundation model":
        st.info(
            "Choose a model provider and use your uploaded documents to generate answers here. "
            "This checks the model with Studio's document search; it does not test an existing assistant's own search or tools."
        )
        render_provider_settings()
        st.button("Continue to evaluation", on_click=navigate, args=("Evaluate",))
        return
    st.write(
        "Send your test questions to an assistant your team already runs, then review its answers. "
        "Use a test version that only answers questions and cannot change records or take actions."
    )
    st.caption(
        "Ask your assistant's developer for its question-and-answer web address and access details. "
        "They can also confirm the question and answer field names below."
    )
    if config.hosted_sessions_enabled():
        st.caption(
            "Use a public HTTPS address. Private network addresses and redirects are blocked. "
            "Your access key stays in this temporary session and is excluded from saved connection settings."
        )
    st.caption(
        "No calls happen until you explicitly run a connection check or evaluation. Action-taking agents are outside this beta's scope."
    )
    with st.expander("Connection settings from your engineer"):
        st.caption(
            "Most assistants need only the fields below. Your engineer can supply a settings file for a custom request; its details stay behind the scenes."
        )
        imported = st.file_uploader(
            "Import connection settings",
            type=["json"],
            key="connection_settings_import",
            **hosted_upload_options(min(config.MAX_UPLOAD_BYTES, config.MAX_EXTERNAL_REQUEST_BYTES)),
        )
        if imported is not None and st.button("Use imported settings"):
            try:
                from src.connection_settings import parse_connection_settings

                settings = parse_connection_settings(imported.getvalue())
                st.session_state.imported_connection_draft = settings
                st.session_state.external_target_secret = ""
                st.success(
                    "Settings loaded. Check the test name and web address, enter the access key if needed, then save the connection."
                )
            except ValueError as exc:
                st.error(safe_display_text(exc))
    values = dict(st.session_state.get("imported_connection_draft") or st.session_state.external_target_config)
    stored_request = values.get("request_template") or {"input": "${question}"}
    simple_request = len(stored_request) == 1 and next(iter(stored_request.values())) == "${question}"
    stored_headers = values.get("headers") or {}
    methods = ["POST", "GET"] if config.hosted_sessions_enabled() else ["POST", "GET", "PUT", "PATCH"]
    saved_auth = (
        "No authentication"
        if values and not stored_headers
        else ("Bearer token" if not stored_headers or "Authorization" in stored_headers else "Custom secret header")
    )
    with st.form("external_connection"):
        name = st.text_input(
            "Name for this test",
            values.get("name", "Support assistant"),
            max_chars=120,
            help="Choose any label you will recognize later, such as Support assistant — September test.",
        )
        endpoint = st.text_input(
            "Your assistant’s web address",
            values.get("endpoint", ""),
            placeholder="https://staging.example.com/answer",
            help=(
                "Ask its developer for the HTTPS address that accepts a question and returns an answer. "
                "They may call this the API endpoint. A normal chat-page address usually will not work."
            ),
        )
        c1, c2 = st.columns(2)
        question_field = c1.text_input(
            "Question field in your request",
            next(iter(stored_request)) if simple_request else "input",
            help='For {"input":"a question"}, enter input.',
        )
        answer_path = c2.text_input(
            "Answer field in the response",
            values.get("response_mappings", {}).get("answer", "$.answer"),
            help='For {"answer":"..."}, use $.answer. Nested fields: $.data.answer.',
        )
        auth_kind = st.selectbox(
            "Authentication",
            ["Bearer token", "No authentication", "Custom secret header"],
            index=["Bearer token", "No authentication", "Custom secret header"].index(saved_auth),
            format_func=lambda value: {
                "Bearer token": "Access token (Bearer)",
                "No authentication": "No key needed",
                "Custom secret header": "API key in a named header",
            }[value],
            help=(
                "This controls how your assistant checks who may use it. Use the option its developer specifies. "
                "Choose No key needed only if they confirm that the test assistant accepts requests without a key."
            ),
        )
        header_name = st.text_input(
            "Secret header name (custom authentication only)",
            next(iter(stored_headers)) if saved_auth == "Custom secret header" else "X-API-Key",
            help="Only needed for API key in a named header. Your developer supplies this name; X-API-Key is one example.",
        )
        secret = st.text_input(
            "Access token or API key",
            type="password",
            value=st.session_state.external_target_secret,
            help="Paste the private access code your developer supplies. For a Bearer token, paste only the token, without the word Bearer.",
        )
        st.caption(
            "Treat this access code like a password. It is hidden while you type and kept only in this open session, "
            "so enter it again next time. It is excluded from saved connections and project downloads. "
            "Leave it empty when No key needed is selected."
        )
        with st.expander("Optional response fields and advanced request"):
            citation_path = st.text_input(
                "Citations field (optional)",
                values.get("response_mappings", {}).get("citations", "$.citations" if not values else ""),
            )
            escalation_path = st.text_input(
                "Escalation field (optional)",
                values.get("response_mappings", {}).get("escalation", "$.escalation" if not values else ""),
            )
            model_path = st.text_input(
                "Reported model field (optional)",
                values.get("response_mappings", {}).get("model", "$.model" if not values else ""),
            )
            st.caption(
                "Missing evidence stays missing. Citations should include source_name or chunk_id; escalation should include should_escalate, destination and urgency."
            )
            use_simple_request = st.checkbox("Send the question using a single request field", value=simple_request)
            if not simple_request:
                st.info("Your engineer's custom request is saved. Leave this option off to keep it unchanged.")
            method = st.selectbox(
                "Request method",
                methods,
                index=methods.index(values.get("method", "POST")) if values.get("method", "POST") in methods else 0,
            )
            streaming = st.checkbox("Streaming SSE response", bool(values.get("streaming", False)))
            timeout = st.number_input(
                "Timeout seconds",
                min_value=0.1,
                max_value=HOSTED_MAX_TIMEOUT_SECONDS if config.hosted_sessions_enabled() else 120.0,
                value=min(
                    float(values.get("timeout_seconds", 30)),
                    HOSTED_MAX_TIMEOUT_SECONDS if config.hosted_sessions_enabled() else 120.0,
                ),
            )
            retries = st.number_input(
                "Retries after transient errors",
                min_value=0,
                max_value=HOSTED_MAX_RETRIES if config.hosted_sessions_enabled() else 3,
                value=min(
                    int(values.get("retry_count", 0)), HOSTED_MAX_RETRIES if config.hosted_sessions_enabled() else 3
                ),
            )
            health_path = st.text_input(
                "Read-only health path (optional)", values.get("health_check_path") or "", placeholder="/health"
            )
            st.caption(
                "A health check needs a read-only health path. Without one, use the explicit test request below. Retries require an idempotent endpoint."
            )
        saved = st.form_submit_button("Save connection", type="primary")
    if saved:
        try:
            if not question_field.strip():
                raise ValueError("Enter the question field your assistant expects.")
            headers = (
                {}
                if auth_kind == "No authentication"
                else {"Authorization" if auth_kind == "Bearer token" else header_name: "secret://SESSION_EXTERNAL_AUTH"}
            )
            mappings = {
                key: path
                for key, path in {
                    **values.get("response_mappings", {}),
                    "answer": answer_path,
                    "citations": citation_path,
                    "escalation": escalation_path,
                    "model": model_path,
                }.items()
                if path
            }
            request = {question_field: "${question}"} if use_simple_request else stored_request
            candidate = {
                "name": name,
                "endpoint": endpoint.strip(),
                "method": method,
                "headers": headers,
                "request_template": request,
                "response_mappings": mappings,
                "timeout_seconds": timeout,
                "retry_count": int(retries),
                "health_check_path": health_path or None,
                "streaming": streaming,
            }
            adapter = ExternalHTTPTarget(ExternalTargetConfig(**candidate))
            database.get_repository().create_target_version(
                st.session_state.workspace_context,
                st.session_state.project_id,
                name,
                "external_api",
                target_configuration_for_storage(adapter.configuration),
            )
            st.session_state.external_target_config = candidate
            st.session_state.pop("imported_connection_draft", None)
            st.session_state.external_target_secret = (
                ("Bearer " + secret.strip())
                if auth_kind == "Bearer token" and secret.strip() and not secret.startswith("Bearer ")
                else secret.strip()
            )
            st.session_state.target_checked_version = None
            track("target_configured", target_type="external_api", outcome="success")
            st.success("Connection saved to this project. Run a check to verify the response format.")
        except (ValueError, TypeError, AuthorizationError) as exc:
            st.error(f"Connection was not saved: {safe_display_text(exc)}")
            track("workflow_error", stage="target", outcome="failure")
    if st.session_state.external_target_config:
        adapter = external_target_from_state()
        st.caption("Connection checks use the last saved configuration. Save again after editing fields.")
        confirmed = st.checkbox(
            "I authorize one connection check against this saved staging endpoint.",
            key=f"target_check_consent_{adapter.version}",
        )
        has_health = bool(st.session_state.external_target_config.get("health_check_path"))
        if st.button("Check connection" if has_health else "Send one test request", disabled=not confirmed):
            try:
                response = (
                    adapter.health_check()
                    if has_health
                    else adapter.execute(
                        {
                            "question": "Connectivity test: please return a brief acknowledgement.",
                            "input": "Connectivity test: please return a brief acknowledgement.",
                            "context": "",
                            "system_prompt": "Return a brief connectivity acknowledgement.",
                            "case_id": "connection-check",
                            "execution_key": uuid.uuid4().hex,
                        }
                    )
                )
                ok = response.status.value == "passed"
                track("target_health_checked", target_type="external_api", outcome="success" if ok else "failure")
                if ok:
                    st.session_state.target_checked_version = external_target_from_state().version
                    st.success(
                        "Connection check passed. This verifies connectivity only; run cases to evaluate answer quality."
                    )
                else:
                    st.error(
                        response.safe_error
                        or "Connection failed. Check the URL, authentication and response fields, then save and retry."
                    )
            except Exception as exc:
                st.error(f"Connection could not be checked: {safe_display_text(exc)}")
        st.button("Continue to evaluation", on_click=navigate, args=("Evaluate",))


def render_run_evaluation(*, live_only: bool = False) -> None:
    if live_only and st.session_state.target_kind == "Synthetic demonstration":
        st.session_state.target_kind = "Direct foundation model"
    st.title("Evaluate this release")
    if st.session_state.project_id is None:
        st.info("Start the sample review or prepare a saved project first.")
        st.button("Go to start", on_click=navigate, args=("Start",))
        return
    if st.session_state.workspace_context.role in {Role.VIEWER, Role.REVIEWER}:
        st.info("An editor or owner must run evaluations. You can review the existing evidence.")
        return
    if config.APP_ACCESS_MODE != "public-demo" and st.session_state.mode != "Demo Mode" and not custom_access():
        return
    ready = (
        bool(st.session_state.chunks) and not st.session_state.eval_df.empty and bool(st.session_state.current_prompt)
    )
    if not st.session_state.chunks:
        st.warning("Load documents before running evaluation.")
    if st.session_state.eval_df.empty:
        st.warning("Load an evaluation dataset before running evaluation.")

    target_options = ["Synthetic demonstration"]
    if config.APP_ACCESS_MODE != "public-demo":
        target_options += ["Direct foundation model"]
        if external_connections_available():
            target_options += ["External assistant/API"]
    if live_only:
        target_options = [value for value in target_options if value != "Synthetic demonstration"]
    if not target_options:
        st.info("Live evaluations are unavailable in the public sample.")
        return
    if st.session_state.target_kind not in target_options:
        st.session_state.target_kind = target_options[0]
    if st.session_state.get("_evaluation_target") not in target_options:
        st.session_state._evaluation_target = st.session_state.target_kind
    target_kind = st.radio(
        "Evaluation target",
        target_options,
        format_func=lambda value: TARGET_LABELS.get(value, value),
        key="_evaluation_target",
        horizontal=True,
    )
    st.session_state.target_kind = target_kind
    if target_kind != "Synthetic demonstration" and not custom_access():
        return
    mode = st.radio(
        "What would you like to check?",
        ["Current Prompt Only", "Current Prompt vs Improved Prompt"],
        format_func=lambda value: {
            "Current Prompt Only": "Check current instructions",
            "Current Prompt vs Improved Prompt": "Compare current and candidate instructions",
        }[value],
        horizontal=True,
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
            st.error(f"No {st.session_state.api_provider} key is configured. Open Connect to add your provider key.")
            model = config.PROVIDER_MODELS[selected_provider()][0]
            st.button("Open Connect", on_click=navigate, args=("Connect",))
            ready = False
        else:
            model = st.selectbox("Exact model identifier", direct_models)
            st.success(
                f"Direct {st.session_state.api_provider} execution via {api_key_source()}. Provider failures remain failures."
            )
    else:
        model = None
        try:
            target_adapter = external_target_from_state()
            for value in target_adapter.configuration.headers.values():
                if value.startswith("secret://"):
                    target_adapter.secrets.resolve(value)
            st.success("Assistant connection ready. Its saved settings will be recorded with this review.")
        except Exception as exc:
            st.error(f"Open Connect to complete the endpoint and session credential: {safe_display_text(exc)}")
            st.button("Open Connect", on_click=navigate, args=("Connect",))
            ready = False

    with st.expander("Retrieval, limits and advanced controls"):
        c1, c2, c3, c4 = st.columns(4)
        top_k = c1.slider("Source passages per question", 1, 8, config.DEFAULT_TOP_K)
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
        max_concurrency = (
            1
            if config.is_browser_runtime()
            else c1.slider(
                "Questions running at once",
                1,
                HOSTED_MAX_CONCURRENCY if config.hosted_sessions_enabled() else 16,
                HOSTED_MAX_CONCURRENCY if config.hosted_sessions_enabled() else 4,
            )
        )
        if config.is_browser_runtime():
            c1.caption("One question runs at a time in this browser.")
        max_retries = c2.slider(
            "Retries after temporary errors",
            0,
            HOSTED_MAX_RETRIES if config.hosted_sessions_enabled() else 3,
            min(
                int(st.session_state.external_target_config.get("retry_count", 1)),
                HOSTED_MAX_RETRIES if config.hosted_sessions_enabled() else 3,
            )
            if target_kind == "External assistant/API"
            else 0,
        )
        candidate_tuned_on_dataset = st.checkbox(
            "A candidate in this run was tuned using cases from this dataset",
            help="If selected, the dataset must contain an explicit tuning_disclosure before it can support a launch verdict.",
        )

    prompts = {"Current Prompt": st.session_state.current_prompt}
    if mode == "Current Prompt vs Improved Prompt":
        prompts["Improved Prompt"] = st.session_state.improved_prompt

    calls = len(st.session_state.eval_df) * len(prompts)
    if config.hosted_sessions_enabled():
        st.caption(run_limit_notice())
        if calls > HOSTED_MAX_EXECUTIONS:
            st.error(
                f"This review would run {calls} answers. The hosted limit is {HOSTED_MAX_EXECUTIONS} per review. "
                "Use fewer questions or check one set of instructions at a time."
            )
            ready = False
    st.info(
        f"Preflight: {st.session_state.eval_df['case_id'].nunique() if 'case_id' in st.session_state.eval_df else len(st.session_state.eval_df)} "
        f"unique cases · {calls} planned executions · at most {calls * (1 + max_retries)} attempts including retries · {len(prompts)} candidate(s). "
        f"Provider cost is {'$0 synthetic' if model == 'mock-model' else 'unknown until exact token usage is returned'}."
    )
    run_dataset_quality = dataset_quality_report(
        st.session_state.eval_df,
        available_sources={str(chunk.get("source_name") or "") for chunk in st.session_state.chunks},
        candidate_tuned_on_dataset=candidate_tuned_on_dataset,
    )
    if not run_dataset_quality["launch_eligible"]:
        st.warning(
            "This dataset has unresolved evidence checks. You can run a diagnostic evaluation, "
            "but it cannot support a launch verdict."
        )
        with st.expander("Resolve dataset evidence checks"):
            from src.case_editor import coverage_findings

            for finding in coverage_findings({"quality_report": run_dataset_quality}):
                st.write(finding)
    preflight_fingerprint = version_hash(
        {
            "project": st.session_state.project_id,
            "dataset": st.session_state.eval_df.to_dict("records"),
            "chunks": st.session_state.chunks,
            "prompts": prompts,
            "target": target_kind,
            "target_version": target_adapter.version if target_adapter else model,
            "top_k": top_k,
            "similarity": similarity_threshold,
            "retries": max_retries,
            "concurrency": max_concurrency,
            "latency_gate": latency_threshold,
            "cost_gate": cost_threshold,
            "credential_digest": hashlib.sha256(
                (
                    effective_api_key()
                    if target_kind == "Direct foundation model"
                    else st.session_state.external_target_secret
                ).encode()
            ).hexdigest(),
        }
    )
    confirmed = (
        True
        if target_kind == "Synthetic demonstration"
        else st.checkbox(
            "I authorize these external calls using approved test data and accept the provider cost.",
            key=f"run_consent_{preflight_fingerprint}",
        )
    )
    if st.button("Run Evaluation", type="primary", disabled=not (ready and confirmed)):
        started = time.monotonic()
        track(
            "run_started",
            target_type={
                "Synthetic demonstration": "synthetic_mock",
                "Direct foundation model": "foundation_model",
                "External assistant/API": "external_api",
            }[target_kind],
            synthetic=model == "mock-model",
            execution_count=calls,
        )
        progress = st.progress(0)
        status = st.empty()

        def update_progress(done: int, total: int) -> None:
            progress.progress(done / total)
            status.write(f"Completed {done} of {total} executions.")

        evaluation_frame = st.session_state.eval_df.copy()
        if model == "mock-model" and mock_scenario != "__per_case__":
            evaluation_frame["mock_scenario"] = mock_scenario
        try:
            with st.spinner("Checking answers and saving progress…"):
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
            st.error(f"Run could not start safely: {safe_display_text(exc)}")
            track("workflow_error", stage="run", outcome="failure")
            return
        st.session_state.last_results = charts.prepare_results(results)
        st.session_state.last_top_k = top_k
        st.session_state.similarity_threshold = similarity_threshold
        counts = execution_summary(results)
        track(
            "run_completed",
            synthetic=model == "mock-model",
            execution_count=len(results),
            scored_count=counts["quality_scored_executions"],
            error_count=counts["infrastructure_errors"],
            duration_ms=(time.monotonic() - started) * 1000,
            outcome="partial" if counts["infrastructure_errors"] else "success",
        )
        navigate("Review")
        st.rerun()


def render_results_dashboard() -> None:
    st.title("Your release review")
    df = charts.prepare_results(st.session_state.last_results)
    if df.empty:
        st.info("Run an evaluation to review its evidence.")
        return
    counts = execution_summary(df)
    synthetic = bool(df.get("target_type", pd.Series(dtype=str)).eq("synthetic_mock").any())
    if synthetic:
        st.warning(
            "Synthetic demonstration — no launch verdict. These fictional answers illustrate the review; they say nothing about your assistant's quality."
        )
    st.caption(
        "Separate missing executions from observed answer problems. Review findings against the source before changing a release."
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Cases checked", counts["unique_test_cases"])
    c2.metric("Answers needing attention", counts["quality_failures"])
    c3.metric("Execution errors", counts["infrastructure_errors"])
    if counts["infrastructure_errors"]:
        if df.get("target_type", pd.Series("", index=df.index)).eq("synthetic_mock").all():
            st.error(
                f"{counts['infrastructure_errors']} simulated connection failures are included in this sample. These calls are excluded from quality averages. No external calls were made."
            )
        else:
            st.error(
                f"{counts['infrastructure_errors']} calls did not produce usable answers. Fix connection or provider errors and rerun; these calls are excluded from quality averages."
            )
    quality = df[df.get("execution_status", pd.Series("passed", index=df.index)).eq("passed")]
    failures = quality[quality["failure_type"].ne("Passed")]
    st.subheader("What failed, and what to change next")
    if failures.empty:
        st.info(
            "No automatic answer failure was flagged among completed calls. Missing coverage, calibration and uncertain evidence can still block a release assessment."
        )
    else:
        priorities = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        ordered = failures.assign(
            _priority=failures.get("severity", pd.Series("medium", index=failures.index)).map(priorities).fillna(2)
        ).sort_values("_priority")
        rows = []
        for _, row in ordered.head(5).iterrows():
            detail = failure_presentation(row.to_dict())
            rows.append(
                {
                    "Question": safe_display_text(row.get("question")),
                    "Severity": row.get("severity", "Review"),
                    "Finding": detail["root_cause"],
                    "Next action": detail["recommended_action"],
                }
            )
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.caption(
            f"Showing the first {min(5, len(failures))} of {len(failures)} flagged answers. Inspect failures for each answer, source passage and evaluator reason."
        )
        first = ordered.iloc[0]
        detail = failure_presentation(first.to_dict())
        with st.expander("Inspect the first finding", expanded=True):
            st.write(safe_display_text(first.get("question")))
            st.markdown("**Why it was flagged**")
            st.write(detail["why_failed"])
            c1, c2 = st.columns(2)
            c1.markdown("**Expected behavior**")
            c1.write(detail["expected_behavior"])
            c2.markdown("**Observed answer**")
            c2.write(detail["actual_behavior"])
            for source in detail["source_passages"][:2]:
                st.caption(f"Source: {source['document']} · {source['location']}")
                st.text(source["passage"])
            st.info(detail["recommended_action"])
    st.subheader("What this evidence supports")
    candidates = evaluate_candidates(df)
    for position, evaluation in enumerate(candidates.values(), start=1):
        st.markdown(f"**{candidate_title(evaluation)}**")
        if len(candidates) > 1:
            st.caption(f"Candidate {position} of {len(candidates)} · assessed separately")
        st.write(evaluation["verdict"])
        check_rows = readiness_check_rows(evaluation)
        blocked = [row for row in check_rows if row["Result"] != "Met"]
        if blocked:
            st.markdown("**What still needs attention**")
            for check in blocked[:4]:
                st.write(f"• {check['Check']}: {check['What it means']}")
        with st.expander("Why this result was given"):
            st.caption(
                "Each check compares the evidence with the requirements for this review. "
                "Meeting one check does not make the assistant ready. Independent human review and representative cases are still required."
            )
            for check in check_rows:
                st.markdown(f"**{check['Check']} — {check['Result']}**")
                st.write(check["What it means"])
            st.caption("The exact instructions, sources, cases and settings are saved automatically with the report.")
    st.info(
        "Better or safer than the baseline? Use Release history after evaluating a revision on the same cases. Synthetic or incompatible evidence cannot establish improvement."
    )
    if not synthetic and st.session_state.get("calibration_result") is None:
        st.button(
            "Check agreement with human reviewers",
            on_click=navigate_to,
            args=("Evaluator Calibration",),
        )
    if not synthetic and st.session_state.workspace_context.role != Role.VIEWER:
        with st.form("review_decision"):
            st.subheader("Record the team's next step")
            decision = st.selectbox(
                "Review outcome", ["Hold release", "Investigate findings", "Proceed to internal testing"]
            )
            action = st.selectbox(
                "Next action",
                [
                    "Review with a domain expert",
                    "Fix the prompt",
                    "Fix the sources",
                    "Fix the target",
                    "Add regression cases",
                    "Rerun evaluation",
                ],
            )
            if st.form_submit_button("Record review decision"):
                decision_code = {
                    "Hold release": "hold",
                    "Investigate findings": "investigate",
                    "Proceed to internal testing": "internal_test",
                }[decision]
                action_code = {
                    "Review with a domain expert": "human_review",
                    "Fix the prompt": "fix_prompt",
                    "Fix the sources": "fix_sources",
                    "Fix the target": "fix_target",
                    "Add regression cases": "add_cases",
                    "Rerun evaluation": "rerun",
                }[action]
                run_ids = df.get("run_id", pd.Series(dtype=int)).dropna().unique()
                track(
                    "decision_recorded",
                    decision=decision_code,
                    next_action=action_code,
                    **({"run_id": int(run_ids[0])} if len(run_ids) == 1 else {}),
                )
                st.success(
                    "Team decision recorded in this workspace's audit log. This does not override evaluator findings or gates."
                )
    with st.expander("Diagnostic charts and execution detail"):
        st.caption("Each candidate remains separate. Charts organize findings and never override evidence limitations.")
        c1, c2 = st.columns(2)
        c1.plotly_chart(charts.failure_distribution_chart(df), use_container_width=True)
        c2.plotly_chart(charts.category_score_chart(df), use_container_width=True)
        st.write(counts["message"])
        st.dataframe(
            readable_frame(
                df[
                    [
                        column
                        for column in [
                            "question",
                            "prompt_name",
                            "execution_status",
                            "failure_type",
                            "safe_error",
                            "attempt_count",
                        ]
                        if column in df
                    ]
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )


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
                "question",
                "execution_status",
                "safe_error",
                "prompt_name",
                "model_name",
                "target_type",
            ]
            if column in infrastructure
        ]
        st.dataframe(readable_frame(infrastructure[error_columns]), hide_index=True, use_container_width=True)
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
        "suggested_fix",
        "prompt_name",
        "model_name",
    ]
    table_cols = [column for column in table_cols if column in filtered]
    st.dataframe(readable_frame(filtered[table_cols]), hide_index=True, use_container_width=True)
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
    for _, row in page_rows.iterrows():
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
                {"Check": metric_label(column), "Observed score": metric_display(column, row.get(column))}
                for column in metric_columns
                if column in row.index
            ]
            if metric_rows:
                st.dataframe(pd.DataFrame(metric_rows), hide_index=True, use_container_width=True)
            with st.expander("Instructions used for this answer"):
                st.text(detail["final_prompt"] or "The instructions were not recorded for this answer.")
                st.caption("Earlier instructions and evaluation settings are kept with the saved evidence.")


def render_prompt_comparison() -> None:
    st.title("Prompt Comparison")
    df = charts.prepare_results(st.session_state.last_results)
    if df.empty or df["prompt_name"].nunique() < 2:
        st.info("In Evaluate, choose Compare current and candidate instructions to see what changed.")
        return
    if "target_type" in df and set(df["target_type"].dropna().astype(str)) == {"synthetic_mock"}:
        st.warning(
            "Synthetic prompt comparison is not a model-quality comparison. Deterministic scenarios ignore prompt "
            "content, so neither prompt can be declared better from this run."
        )
        st.dataframe(readable_frame(charts.prompt_metric_table(df)), hide_index=True, use_container_width=True)
        st.info(charts.insight_summary(df, top_k=st.session_state.last_top_k))
        return
    table = charts.prompt_metric_table(df)
    st.dataframe(readable_frame(table), hide_index=True, use_container_width=True)
    st.plotly_chart(charts.prompt_comparison_chart(df), use_container_width=True)
    st.info(charts.insight_summary(df, top_k=st.session_state.last_top_k))
    if df["model_name"].nunique() > 1:
        st.subheader("Model comparison")
        st.plotly_chart(charts.model_comparison_chart(df), use_container_width=True)
    else:
        st.caption("Model comparison is hidden because only one model was evaluated.")


def render_run_history() -> None:
    st.title("Run History / Comparison")
    render_project_transfer("history")
    if st.session_state.get("project_restore_notice"):
        st.info(st.session_state.project_restore_notice)
    runs = project_runs()
    if runs.empty:
        st.info("No historical runs are available in this workspace.")
        return
    st.dataframe(
        readable_frame(runs[[col for col in ["run_name", "status", "created_at", "target_type"] if col in runs]]),
        hide_index=True,
        use_container_width=True,
    )
    if len(runs) < 2:
        st.info(
            "You have a baseline. Evaluate a revised prompt or assistant with the same cases, then return here to compare."
        )
        st.button("Evaluate a revision", on_click=navigate, args=("Evaluate",))
    labels = {
        f"Review {len(runs) - position} · {display_value(row['run_name'])} · {display_value(row['status'])}": int(
            row["id"]
        )
        for position, (_, row) in enumerate(runs.iterrows())
    }
    baseline_label = st.selectbox("Baseline run", list(labels), index=min(1, len(labels) - 1))
    candidate_label = st.selectbox("Candidate run", list(labels), index=0)
    if st.button("Compare selected runs", type="primary", disabled=baseline_label == candidate_label):
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
        track("comparison_viewed", ranking_supported=comparison.get("ranking_supported", False))
        summary = comparison.get("decision_summary", "Inspect the comparison limitations before deciding.")
        if not comparison.get("ranking_supported", False):
            st.warning(summary)
        elif comparison["regressed"]:
            st.error(summary)
        else:
            st.info(summary)
        for limitation in comparison.get("limitations", []):
            st.warning(limitation)
        c1, c2 = st.columns(2)
        c1.metric("Observed score change", f"{comparison['quality_delta'] * 100:+.1f} percentage points")
        c2.metric("Regressions", len(comparison["regressions"]))

        st.subheader("Candidate summaries")
        columns = st.columns(2)
        for column, side in zip(columns, ["baseline", "candidate"], strict=False):
            column.markdown(f"**{side.title()} run**")
            summaries = comparison["candidate_summaries"][side]
            if not summaries:
                column.info("No candidate evidence is available.")
            for evaluation in summaries.values():
                column.markdown(f"{evaluation['verdict']} · {candidate_title(evaluation)}")
                counts = evaluation.get("counts", {})
                column.caption(
                    f"{counts.get('unique_test_cases', 0)} unique cases · "
                    f"{counts.get('quality_scored_executions', 0)} quality-scored · "
                    f"{counts.get('execution_error_count', 0)} infrastructure errors"
                )

        st.subheader("How the scores changed")
        metric_delta_rows = [
            {
                "Check": metric_label(metric),
                "Earlier review": metric_display(metric, values["baseline"]),
                "New review": metric_display(metric, values["candidate"]),
                "Change": metric_display(metric, values["delta"], delta=True),
            }
            for metric, values in comparison["metric_deltas"].items()
        ]
        st.dataframe(pd.DataFrame(metric_delta_rows), hide_index=True, use_container_width=True)

        st.subheader("Release checks that changed")
        if comparison["gate_changes"]:
            gate_changes = []
            for change in comparison["gate_changes"]:

                def check_state(value):
                    return "Met" if value is True else "Not met" if value is False else "Not recorded"

                gate_changes.append(
                    {
                        "Check": metric_label(change["gate"]),
                        "Earlier review": check_state(change.get("baseline_passed")),
                        "New review": check_state(change.get("candidate_passed")),
                    }
                )
            st.dataframe(pd.DataFrame(gate_changes), hide_index=True, use_container_width=True)
        else:
            st.caption("No launch-gate state or explanation changed.")

        c1, c2 = st.columns(2)
        c1.markdown("**New failures**")
        questions = {
            str(row["case_id"]): str(row.get("question", "Question unavailable"))
            for _, row in pd.concat([baseline, candidate]).iterrows()
            if "case_id" in row
        }
        if comparison["new_failures"]:
            c1.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Question": safe_display_text(questions.get(str(item["case_id"]), "Question unavailable")),
                            "Finding": display_value(item["failure"]),
                        }
                        for item in comparison["new_failures"]
                    ]
                ),
                hide_index=True,
                use_container_width=True,
            )
        else:
            c1.caption("No newly introduced failures.")
        c2.markdown("**Resolved failures**")
        if comparison["resolved_failures"]:
            c2.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Question": safe_display_text(questions.get(str(item["case_id"]), "Question unavailable")),
                            "Finding": display_value(item["failure"]),
                        }
                        for item in comparison["resolved_failures"]
                    ]
                ),
                hide_index=True,
                use_container_width=True,
            )
        else:
            c2.caption("No resolved failures.")

        st.subheader("Failure regressions by severity and category")
        c1, c2 = st.columns(2)
        severity_rows = comparison["failure_count_deltas"]["severity"]
        category_rows = comparison["failure_count_deltas"]["category"]
        c1.dataframe(readable_frame(pd.DataFrame(severity_rows)), hide_index=True, use_container_width=True)
        c2.dataframe(readable_frame(pd.DataFrame(category_rows)), hide_index=True, use_container_width=True)

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
        st.dataframe(readable_frame(pd.DataFrame(operational_rows)), hide_index=True, use_container_width=True)

        st.subheader("What changed between these reviews")
        st.dataframe(pd.DataFrame(version_difference_rows(comparison)), hide_index=True, use_container_width=True)
        st.caption(
            "Exact saved versions are compared automatically. Missing version history limits what this comparison can establish."
        )
        raw_comparison = json.dumps(safe_nested(comparison), ensure_ascii=False, indent=2, default=str)
        with st.expander("Evidence file for your engineer"):
            st.caption(
                "A machine-readable copy retains the exact settings and original measurements for independent verification."
            )
            st.download_button(
                "Download comparison evidence", raw_comparison, "ai_reliability_run_comparison.json", "application/json"
            )


def render_settings_export() -> None:
    st.title("Export and workspace settings")
    st.caption(f"Application release {config.APP_RELEASE} · Evaluation rules {EVALUATOR_VERSION}")
    render_exports()
    st.divider()
    if config.APP_ACCESS_MODE != "public-demo":
        with st.expander("Provider credentials"):
            render_provider_settings()
    st.caption(
        "Product events store counts, timings and choices in this workspace's audit log. "
        "No document text, prompts, answers, credentials or personal data are sent to an analytics service."
    )
    if config.APP_ACCESS_MODE == "public-demo":
        st.info(
            "Sample-only session. No data is written to the shared project database. Reloading starts a fresh demo."
        )
        return
    if st.session_state.workspace_context.role != Role.OWNER:
        st.info("Only a workspace owner can clear results or reset data.")
        return
    with st.expander("Delete workspace data"):
        st.warning("These actions permanently remove data from this workspace. Export a report first.")
        confirmation = st.text_input("Type DELETE WORKSPACE DATA to enable destructive actions")
        if st.button("Clear evaluation results", disabled=confirmation != "DELETE WORKSPACE DATA"):
            database.clear_results(confirm=True)
            st.session_state.last_results = pd.DataFrame()
            st.success("Workspace results deleted.")
        st.button("Reset workspace", disabled=confirmation != "DELETE WORKSPACE DATA", on_click=reset_workspace_data)


def export_clicked(report_format: str, content: str, run_id: int | None) -> None:
    # Streamlit invokes callbacks before init_state: rebind this session explicitly.
    database.initialize_session(st.session_state, dict(st.context.headers))
    database.record_export(report_format, content, run_id, context=st.session_state.workspace_context)
    track("report_exported", format=report_format)


def render_exports() -> None:
    render_project_transfer("exports")
    frame = charts.prepare_results(st.session_state.last_results)
    if frame.empty:
        st.info("Complete an evaluation and select its result to export a report.")
        return
    st.subheader("Share the evidence")
    st.caption(
        "Reports include candidate identity, execution status, gates and limitations. Secrets and detected personal data are redacted. "
        "Redaction cannot identify every confidential detail; review files before sharing."
    )
    ids = frame.get("run_id", pd.Series(dtype=int)).dropna().unique()
    run_id = int(ids[0]) if len(ids) == 1 else None
    content = html_report(frame, redact_personal_data=True)
    st.download_button(
        "Download readable report",
        content,
        "release-review.html",
        "text/html",
        on_click=export_clicked,
        args=("html", content, run_id),
    )
    with st.expander("Evidence files for your engineer"):
        st.caption(
            "These optional files preserve exact measurements and saved versions for verification or other tools."
        )
        for fmt, create, mime in [("json", json_report, "application/json"), ("csv", csv_report, "text/csv")]:
            content = create(frame, redact_personal_data=True)
            st.download_button(
                f"Download {fmt.upper()} evidence",
                content,
                f"release-review.{fmt}",
                mime,
                on_click=export_clicked,
                args=(fmt, content, run_id),
            )


def render_review() -> None:
    if st.session_state.last_results.empty:
        st.title("Review the evidence")
        st.info("No result is selected. Run the sample or evaluate a prepared project.")
        st.button("Go to start", on_click=navigate, args=("Start",))
        return
    run_key = tuple(st.session_state.last_results.get("run_id", pd.Series(dtype=int)).dropna().unique())
    if st.session_state.get("viewed_run_key") != run_key:
        track(
            "report_viewed",
            duration_ms=min(86_400_000, (time.monotonic() - st.session_state.session_started_at) * 1000),
        )
        st.session_state.viewed_run_key = run_key
    choice = st.radio(
        "Review view", ["Decision summary", "Inspect failures", "Export evidence"], key="review_view", horizontal=True
    )
    if choice == "Inspect failures":
        render_failure_analysis()
    elif choice == "Export evidence":
        render_exports()
    else:
        render_results_dashboard()


def request_headers() -> dict:
    try:
        return dict(st.context.headers)
    except Exception:
        return {}


def bind_current_session():
    return initialize_session(st.session_state, request_headers())


def reset_workspace_data() -> None:
    # Widget callbacks run before init_state, so rebind this visitor first.
    bind_current_session()
    database.reset_current_workspace(confirm=True)
    # Clear saved reviews, uploads, and keys before new widgets render. Public
    # sessions also delete their private DB; authenticated storage keeps its audit.
    end_public_session(st.session_state)


def clear_in_app_provider_key(provider: str) -> None:
    keys = dict(st.session_state.get("provider_api_keys", {}))
    keys[provider] = ""
    st.session_state.provider_api_keys = keys
    st.session_state[f"_provider_key_input_{provider}"] = ""


def public_session_mode() -> bool:
    check = getattr(config, "public_sessions_enabled", None)
    return bool(check()) if check is not None else os.getenv("AUTH_MODE", "").lower() == "public-session"


def external_connections_available() -> bool:
    # Streamlit can rerun this file while an older config module is cached.
    # The interpreter platform is authoritative and independent of that cache.
    if sys.platform == "emscripten":
        return False
    if config.hosted_sessions_enabled():
        return True
    return not public_session_mode() or bool(config.EXTERNAL_TARGET_ALLOWED_HOSTS)


def navigate_to(page: str, message: str = "") -> None:
    st.session_state._next_page = page
    if message:
        st.session_state._workflow_message = message
    st.rerun()


def install_review_workspace(workspace: dict) -> None:
    baseline = evaluate_review_workspace(workspace)
    candidate = evaluate_review_workspace(workspace, "candidate")
    st.session_state.pop("_show_resume_workspace", None)
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


def render_saved_import() -> None:
    if not custom_access(require_project=True):
        return
    with st.expander("Resume a saved workspace", expanded=st.session_state.get("_show_resume_workspace", False)):
        st.caption(
            "Upload the workspace file you downloaded earlier to continue with its sources, answers and reviews."
        )
        saved = st.file_uploader(
            "Workspace file exported by this app",
            type=["json"],
            key="resume_saved_workspace",
            **hosted_upload_options(),
        )
        if st.button("Resume review", disabled=saved is None):
            try:
                install_review_workspace(read_review_workspace(saved.getvalue()))
                navigate_to(
                    "Review saved answers",
                    "Workspace restored. Existing review hashes were checked against its inputs.",
                )
            except Exception as exc:
                workflow_error(exc, "restore this workspace")
    st.subheader("1. Add your files")
    st.write("Use a question file with expected answers, the source documents, and the assistant's saved answers.")
    st.download_button("Download starter files", starter_pack(), "saved-answer-starter.zip", "application/zip")
    if st.button("Use the three-answer sample", key="saved_import_sample"):
        install_review_workspace(sample_review_workspace())
        navigate_to("Review saved answers", "Three fictional answers loaded. Review their sources to try the workflow.")
    with st.form("saved_import_form"):
        source_files, dataset_file, answer_file = [], None, None
        source_files = st.file_uploader(
            "Source documents",
            type=UPLOAD_TYPES,
            accept_multiple_files=True,
            key="saved_sources_upload",
            help="For source JSON, use the passage format in the starter files. TXT, Markdown, PDF and DOCX also work.",
            **hosted_upload_options(),
        )
        c1, c2 = st.columns(2)
        dataset_file = c1.file_uploader(
            "Questions and expected answers",
            type=EVALUATION_UPLOAD_TYPES,
            key="saved_questions_upload",
            **hosted_upload_options(),
        )
        answer_file = c2.file_uploader(
            "Saved assistant answers",
            type=["json", "jsonl", "csv"],
            key="saved_answers_upload",
            **hosted_upload_options(),
        )
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
        if not source_files or dataset_file is None or answer_file is None:
            st.warning("Add the sources, question file, and answer file to continue.")
        elif not all(value.strip() for value in (target_name, target_version, captured_at)):
            st.warning("Add an assistant name, a version or batch name, and the capture time.")
        else:
            try:
                dataset = read_eval_dataset(dataset_file.name, dataset_file.getvalue())
                responses = read_response_file(answer_file.name, answer_file.getvalue())
                sources = read_reference_uploads(source_files)
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
        format_func=lambda value: f"{'Pending' if value in pending else 'Reviewed'} · {safe_display_text(questions[value])}",
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
                for index, citation in enumerate(citations, start=1):
                    detail = citation if isinstance(citation, dict) else {"source": citation}
                    st.write(
                        f"Source {index}: {safe_display_text(detail.get('source_name') or detail.get('source') or detail.get('title') or 'Source reference supplied')}"
                    )
                    if detail.get("quote"):
                        render_plain_text(str(detail["quote"]))
                st.caption("Exact citation references are retained in the evidence export.")
        with st.expander("Automatic check · advisory only"):
            st.write(safe_display_text(row.get("failure_type", "Not available")))
            st.caption(
                "This result is not your review decision. A high score does not prove that the answer is correct."
            )
            explanation = failure_presentation(row)
            st.write(explanation["why_failed"])
            st.info(explanation["recommended_action"])
            st.caption("The review history retains the precise automatic checks.")
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
                f"{safe_display_text(chunk['source_name'])} · {safe_display_text(chunk.get('section') or 'Source passage')}",
                expanded=len(relevant) <= 2,
            ):
                render_plain_text(chunk["chunk_text"])
        if expected_ids:
            with st.expander("All uploaded sources"):
                for chunk in sources:
                    st.markdown(f"**{safe_display_text(chunk['source_name'])}**")
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
        uploaded = st.file_uploader(
            "Replacement answer file",
            type=["json", "jsonl", "csv"],
            key="replacement_upload",
            **hosted_upload_options(),
        )
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
            readable_frame(
                table.assign(question=table["case_id"].map(baseline.set_index("case_id")["question"]))[
                    ["question", "status", "baseline_decision", "candidate_decision", "reason"]
                ]
            ),
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
    resuming = st.session_state.get("_show_resume_workspace", False)
    if workspace and resuming:
        st.caption("Your current review stays available until another workspace is successfully restored.")
        if st.button("Back to current review", key="cancel_resume"):
            st.session_state.pop("_show_resume_workspace", None)
            st.rerun()
    if not workspace or resuming:
        st.progress(0.0, text="Step 1 of 3 · Add files, then review answers and compare replacements")
        render_saved_import()
        return
    baseline = st.session_state.offline_baseline
    candidate = st.session_state.offline_candidate
    extraction_notices = source_extraction_warnings(workspace["sources"])
    if extraction_notices:
        st.warning(
            "Some source content needs an extraction check. Open the original documents before deciding whether "
            "an answer is supported; the imported passages may be incomplete. These notices stay in your exports."
        )
        with st.expander("Source extraction notices", expanded=True):
            for notice in extraction_notices:
                st.text(notice)
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
    st.download_button("Download readable report", html_report(frame), f"{batch}-answer-review.html", "text/html")
    with st.expander("Evidence files for your engineer"):
        st.download_button(
            "Download JSON evidence", json_report(frame), f"{batch}-answer-review.json", "application/json"
        )
        st.download_button("Download CSV evidence", csv_report(frame), f"{batch}-answer-review.csv", "text/csv")
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
    if not custom_access(require_project=True):
        return
    st.title("Evaluate live assistant")
    st.caption("Prepare sources and questions, collect new answers, then inspect the evidence.")
    if not external_connections_available():
        st.info(
            "This public app can generate answers with a model provider using Studio's source retrieval. "
            "To check your deployed support or RAG assistant, collect its answers and choose Review saved answers. "
            "That workflow preserves the actual answers from your assistant."
        )
    steps = ["1. Sources", "2. Questions", "3. Connect and run", "4. Results"]
    requested = st.session_state.pop("_next_live_step", None)
    if requested in steps:
        st.session_state.live_step = requested
    step = st.radio("Evaluation steps", steps, horizontal=True, key="live_step")
    st.progress(steps.index(step) / 3, text=step)
    if step == steps[0]:
        st.write("Add the documents that contain the answers your assistant should use.")
        files = st.file_uploader(
            "Source documents",
            type=UPLOAD_TYPES,
            accept_multiple_files=True,
            key="live_source_upload",
            **hosted_upload_options(),
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
            "Question set with expected answers",
            type=EVALUATION_UPLOAD_TYPES,
            key="live_questions_upload",
            **hosted_upload_options(),
        )
        upload_digest = hashlib.sha256(uploaded.getvalue()).hexdigest() if uploaded is not None else None
        if uploaded is not None and upload_digest != st.session_state.get("loaded_dataset_upload"):
            try:
                st.session_state.eval_df = read_eval_dataset(uploaded.name, uploaded.getvalue())
                save_dataset_snapshot()
                st.session_state.loaded_dataset_upload = upload_digest
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


def main() -> None:
    apply_theme()
    try:
        init_state()
    except HostedLimitError as exc:
        st.error(safe_display_text(exc))
        st.button("Try opening the workspace again")
        st.stop()
    except (PermissionError, ValueError):
        st.error(
            "Workspace access could not be authorized. Ask the workspace owner to check the access mode and identity configuration."
        )
        st.stop()
    requested = st.session_state.pop("_next_page", None)
    aliases = {
        "Overview": "Start",
        "Project Setup": "Prepare",
        "Target Setup": "Connect",
        "Run Evaluation": "Evaluate",
        "Results Dashboard": "Review",
        "Run History / Comparison": "History",
    }
    if requested:
        selected = aliases.get(requested, requested)
        if selected in {"Start", "Prepare", "Connect", "Evaluate", "Review", "History"}:
            st.session_state.navigation = selected
            st.session_state.advanced_tool = "Choose a tool"
        else:
            st.session_state.advanced_tool = selected
            st.session_state.navigation = None
    if st.session_state.get("pending_navigation"):
        st.session_state.navigation = st.session_state.pop("pending_navigation")
        st.session_state.advanced_tool = "Choose a tool"
    if st.session_state.get("pending_prepare_step"):
        st.session_state.prepare_step = st.session_state.pop("pending_prepare_step")

    def reset_advanced_tool():
        st.session_state.advanced_tool = "Choose a tool"

    def select_advanced_tool():
        if st.session_state.advanced_tool != "Choose a tool":
            st.session_state.navigation = None
        elif st.session_state.navigation is None:
            st.session_state.navigation = "Start"

    st.sidebar.title("AI Reliability Studio")
    st.sidebar.caption("Evidence for your next support-assistant release")
    page = st.sidebar.radio(
        "Workflow",
        ["Start", "Prepare", "Connect", "Evaluate", "Review", "History"],
        key="navigation",
        on_change=reset_advanced_tool,
    )
    with st.sidebar.expander("Advanced tools"):
        tool = st.selectbox(
            "Open a tool",
            [
                "Choose a tool",
                "Review saved answers",
                "Evaluate live assistant",
                "Knowledge Base",
                "System Prompt",
                "Evaluation Dataset",
                "Evaluator Calibration",
                "Failure Analysis",
                "Prompt Comparison",
                "Settings / Export",
            ],
            key="advanced_tool",
            on_change=select_advanced_tool,
        )
    st.sidebar.divider()
    if config.APP_ACCESS_MODE == "public-demo":
        st.sidebar.info("Private sample session · Temporary · No external calls")
    elif config.is_browser_runtime():
        st.sidebar.caption("Private browser workspace · Download your work before closing this tab")
    elif config.hosted_sessions_enabled():
        st.sidebar.caption("Private hosted session · Temporary · Download your project before leaving")
    elif config.APP_ACCESS_MODE == "local":
        st.sidebar.caption("Private local workspace · Saved on this computer")
    else:
        st.sidebar.caption("Authenticated workspace")
    if st.session_state.get("public_session_notice"):
        st.sidebar.caption(st.session_state.public_session_notice)
    if public_session_mode():
        st.sidebar.button("End session and clear my data", on_click=end_public_session, args=(st.session_state,))
    if st.session_state.project_id:
        st.sidebar.write(safe_display_text(st.session_state.project.get("name")))
        st.sidebar.caption(f"{len(st.session_state.chunks)} passages · {len(st.session_state.eval_df)} cases")
    pages = {
        "Start": render_overview,
        "Review saved answers": render_saved_answers,
        "Evaluate live assistant": render_live_assistant,
        "Prepare": render_prepare,
        "Connect": render_target_setup,
        "Evaluate": render_run_evaluation,
        "Review": render_review,
        "History": render_run_history,
        "Knowledge Base": render_knowledge_base,
        "System Prompt": render_system_prompt,
        "Evaluation Dataset": render_eval_dataset,
        "Evaluator Calibration": render_evaluator_calibration,
        "Failure Analysis": render_failure_analysis,
        "Prompt Comparison": render_prompt_comparison,
        "Settings / Export": render_settings_export,
    }
    if tool != "Choose a tool":
        st.button("Back to start", key="return_to_start", on_click=navigate, args=("Start",))
    if message := st.session_state.pop("_workflow_message", None):
        st.success(message)
    if warning := st.session_state.pop("_workflow_warning", None):
        st.warning(warning)
    if tool != "Review saved answers":
        st.session_state.pop("_show_resume_workspace", None)
    try:
        pages[tool if tool != "Choose a tool" else page]()
    except sqlite3.DatabaseError as exc:
        if not config.hosted_sessions_enabled() or "full" not in str(exc).lower():
            raise
        st.error(
            "This session has reached its storage limit. Download your project to keep your saved work, "
            "then end this session before starting another review."
        )
        st.button("Open saved projects and downloads", on_click=navigate, args=("Start",))


if __name__ == "__main__":
    main()
