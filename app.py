from __future__ import annotations

import html
import json

import pandas as pd
import streamlit as st

from src import charts, config, database
from src.chunker import chunk_documents
from src.evaluator import normalize_eval_dataset, run_evaluation, validate_eval_dataset
from src.sample_data import (
    default_prompts,
    load_sample_documents,
    load_sample_eval_dataset,
    sample_project_metadata,
)
from src.suggestions import generate_improved_prompt
from src.vector_store import SimpleVectorStore


st.set_page_config(page_title="AI Reliability Studio", page_icon="ARS", layout="wide")


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
        .block-container {padding-top: 1.3rem; padding-bottom: 2rem; max-width: 1440px;}
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
            color: #f8fafc !important;
        }
        .stAppHeader button,
        .stAppToolbar button,
        .stAppDeployButton button {
            color: #f8fafc !important;
            border-color: rgba(248, 250, 252, .35) !important;
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
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_state() -> None:
    database.init_db()
    prompts = default_prompts()
    st.session_state.setdefault("mode", "Demo Mode")
    st.session_state.setdefault("openai_api_key", "")
    st.session_state.setdefault("project_id", None)
    st.session_state.setdefault("project", sample_project_metadata())
    st.session_state.setdefault("documents", [])
    st.session_state.setdefault("chunks", database.load_chunks())
    st.session_state.setdefault("eval_df", pd.DataFrame())
    st.session_state.setdefault("current_prompt", prompts["Current Prompt"])
    st.session_state.setdefault("improved_prompt", prompts["Improved Prompt"])
    st.session_state.setdefault("last_results", charts.prepare_results(database.latest_results_df()))
    st.session_state.setdefault("last_top_k", config.DEFAULT_TOP_K)


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
    return (
        (st.session_state.get("openai_api_key") or "").strip()
        or streamlit_secret_api_key()
        or config.OPENAI_API_KEY
    )


def api_key_source() -> str:
    if (st.session_state.get("openai_api_key") or "").strip():
        return "In-app session key"
    if streamlit_secret_api_key():
        return "Streamlit secrets"
    if config.OPENAI_API_KEY:
        return ".env key"
    return "No API key"


def api_key_status_label() -> str:
    return "Available" if effective_api_key() else "Not available"


def model_options() -> list[str]:
    return config.available_models(api_key=effective_api_key())


def streamlit_secret_api_key() -> str:
    try:
        return str(st.secrets.get("OPENAI_API_KEY", "") or "").strip()
    except Exception:
        return ""


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
    database.clear_database()


def save_uploaded_documents(files) -> None:
    documents = []
    for uploaded in files:
        suffix = uploaded.name.lower().split(".")[-1]
        if suffix not in {"md", "markdown", "txt"}:
            st.warning(f"{uploaded.name} skipped. TXT and Markdown uploads are supported in this MVP.")
            continue
        text = uploaded.getvalue().decode("utf-8", errors="ignore")
        documents.append({"filename": uploaded.name, "path": uploaded.name, "text": text.strip()})
    if documents:
        chunks = chunk_documents(documents)
        st.session_state.documents = documents
        st.session_state.chunks = chunks
        database.save_documents_and_chunks(documents, chunks, project_id=st.session_state.project_id)


def bool_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin(["true", "1", "yes", "y"])


def parse_jsonish(value):
    if isinstance(value, list):
        return value
    try:
        return json.loads(value)
    except Exception:
        return []


def render_plain_text(text: str) -> None:
    safe = html.escape(text or "")
    st.markdown(f"<div class='chunk-text'>{safe}</div>", unsafe_allow_html=True)


def render_overview() -> None:
    st.markdown(
        """
        <div class="hero">
          <h1>AI Reliability Studio</h1>
          <p><strong>QA and benchmarking dashboard for testing LLM assistants before launch.</strong></p>
          <p>Upload documents, system prompt, and expected-answer test cases. The app runs the assistant and scores correctness, grounding, hallucination risk, citations, escalation behavior, latency, and cost.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Load Sample Fintech Demo", type="primary", use_container_width=True):
            load_demo()
            st.success("FinSure demo loaded.")
    with c2:
        if st.button("Start Custom Upload Mode", use_container_width=True):
            start_custom_mode()
            st.success("Custom upload mode started.")

    st.markdown(f"<span class='mode-pill'>{st.session_state.mode}</span>", unsafe_allow_html=True)
    if not effective_api_key():
        st.info("Mock Demo Mode is active. Real prompt/model evaluation requires an OpenAI API key in Settings, Streamlit secrets, or `.env`.")
    else:
        st.success(f"Real LLM Mode is available using {api_key_source()}.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Documents", len(st.session_state.documents))
    c2.metric("Chunks", len(st.session_state.chunks))
    c3.metric("Eval cases", len(st.session_state.eval_df))
    c4.metric("Latest results", len(st.session_state.last_results))

    st.subheader("Product flow")
    st.dataframe(
        pd.DataFrame(
            [
                ["1", "Load sample demo or upload custom data"],
                ["2", "Add company documents and paste the current system prompt"],
                ["3", "Generate and edit an improved prompt"],
                ["4", "Upload expected-answer evaluation cases"],
                ["5", "Run evaluation and review launch readiness"],
                ["6", "Compare prompts, analyze failures, and export results"],
            ],
            columns=["Step", "Action"],
        ),
        hide_index=True,
        use_container_width=True,
    )


def render_project_setup() -> None:
    st.title("Project Setup")
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
        uploaded = st.file_uploader("Upload custom Markdown or TXT files", type=["md", "markdown", "txt"], accept_multiple_files=True)
        if uploaded and st.button("Index uploaded documents"):
            save_uploaded_documents(uploaded)
            st.success(f"Indexed {len(st.session_state.chunks)} chunks.")
        docs_df = database.documents_df()
        st.metric("Chunk count", len(st.session_state.chunks))
        if not docs_df.empty:
            st.dataframe(docs_df, hide_index=True, use_container_width=True)
    with c2:
        st.subheader("Retrieval test")
        question = st.text_input("Sample question", "Can I close my account if I have an active loan?")
        top_k = st.slider("Top chunks", 1, 8, config.DEFAULT_TOP_K, key="kb_top_k")
        if st.button("Test retrieval") and st.session_state.chunks:
            store = SimpleVectorStore()
            store.build(st.session_state.chunks)
            results = store.retrieve(question, top_k=top_k, similarity_threshold=0.0)
            for chunk in results:
                with st.expander(f"{chunk['source_name']} | similarity {chunk['similarity']:.2f}"):
                    render_plain_text(chunk["chunk_text"])
        st.subheader("Chunk preview")
        preview = pd.DataFrame(st.session_state.chunks[:10])
        if not preview.empty:
            st.dataframe(preview[["source_name", "chunk_index", "chunk_text"]], hide_index=True, use_container_width=True)


def render_system_prompt() -> None:
    st.title("System Prompt")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Load sample current prompt"):
            st.session_state.current_prompt = default_prompts()["Current Prompt"]
        current = st.text_area("Current system prompt", st.session_state.current_prompt, height=340)
    with c2:
        if st.button("Generate improved prompt", type="primary"):
            st.session_state.improved_prompt = generate_improved_prompt(
                current,
                st.session_state.project.get("industry") or "regulated fintech support",
            )
        improved = st.text_area("Improved system prompt", st.session_state.improved_prompt, height=340)

    st.session_state.current_prompt = current
    st.session_state.improved_prompt = improved
    if st.button("Save prompts"):
        database.save_prompt(st.session_state.project_id, "Current Prompt", current, "current")
        database.save_prompt(st.session_state.project_id, "Improved Prompt", improved, "improved")
        st.success("Prompts saved.")


def render_eval_dataset() -> None:
    st.title("Evaluation Dataset")
    c1, c2 = st.columns([0.34, 0.66])
    with c1:
        if st.button("Load sample evaluation dataset", type="primary"):
            st.session_state.eval_df = normalize_eval_dataset(load_sample_eval_dataset())
            st.success("Sample evaluation dataset loaded.")
        uploaded = st.file_uploader("Upload evaluation CSV", type=["csv"])
        if uploaded is not None:
            df = pd.read_csv(uploaded)
            try:
                st.session_state.eval_df = normalize_eval_dataset(df)
                st.success("Evaluation CSV validated and loaded.")
            except ValueError as exc:
                st.error(str(exc))
        df = st.session_state.eval_df
        if not df.empty:
            c1a, c1b = st.columns(2)
            c1a.metric("Questions", len(df))
            c1b.metric("Escalation cases", int(bool_series(df["should_escalate"]).sum()))
            st.bar_chart(df["category"].value_counts())
            st.bar_chart(df["expected_source"].value_counts())
    with c2:
        if st.session_state.eval_df.empty:
            st.info("Required columns: question, expected_answer, expected_source, category, should_escalate")
        else:
            st.dataframe(st.session_state.eval_df, hide_index=True, use_container_width=True)


def render_run_evaluation() -> None:
    st.title("Run Evaluation")
    ready = bool(st.session_state.chunks) and not st.session_state.eval_df.empty and bool(st.session_state.current_prompt)
    if not st.session_state.chunks:
        st.warning("Load documents before running evaluation.")
    if st.session_state.eval_df.empty:
        st.warning("Load an evaluation dataset before running evaluation.")

    if not effective_api_key():
        st.info("No OpenAI API key is available, so evaluations will run with the deterministic Mock Model. Add a key in Settings for Real LLM Mode.")
    else:
        st.success(f"Real LLM Mode available via {api_key_source()}. You can still choose Mock Model for a free deterministic demo.")

    mode = st.radio("Evaluation mode", ["Current Prompt Only", "Current Prompt vs Improved Prompt"], horizontal=True)
    model = st.selectbox("Model", model_options())
    c1, c2, c3 = st.columns(3)
    top_k = c1.slider("top_k retrieval", 1, 8, config.DEFAULT_TOP_K)
    latency_threshold = c2.number_input("Latency threshold (ms)", min_value=100, value=config.LATENCY_THRESHOLD_MS, step=100)
    cost_threshold = c3.number_input("Cost threshold (USD)", min_value=0.0, value=config.COST_THRESHOLD_USD, step=0.005, format="%.3f")

    prompts = {"Current Prompt": st.session_state.current_prompt}
    if mode == "Current Prompt vs Improved Prompt":
        prompts["Improved Prompt"] = st.session_state.improved_prompt

    if st.button("Run Evaluation", type="primary", disabled=not ready):
        progress = st.progress(0)
        status = st.empty()

        def update_progress(done: int, total: int) -> None:
            progress.progress(done / total)
            status.write(f"Scored {done} of {total} prompt/question cases.")

        with st.spinner("Running reliability evaluation..."):
            results = run_evaluation(
                eval_df=st.session_state.eval_df,
                chunks=st.session_state.chunks,
                prompts=prompts,
                model_name=model,
                top_k=top_k,
                similarity_threshold=0.0,
                latency_threshold_ms=latency_threshold,
                cost_threshold_usd=cost_threshold,
                mode=mode,
                project_id=st.session_state.project_id,
                progress_callback=update_progress,
                api_key=effective_api_key(),
            )
        st.session_state.last_results = charts.prepare_results(results)
        st.session_state.last_top_k = top_k
        st.success(f"Evaluation complete: {len(results)} scored rows.")
        st.dataframe(st.session_state.last_results.head(20), use_container_width=True, hide_index=True)


def render_results_dashboard() -> None:
    st.title("Results Dashboard")
    df = charts.prepare_results(st.session_state.last_results)
    if df.empty:
        st.info("Run an evaluation to populate the dashboard.")
        return
    summary = charts.metric_summary(df)
    c = st.columns(5)
    c[0].metric("Total test questions", summary["total_questions"])
    c[1].metric("Overall reliability", f"{summary['overall_score']:.1f}%")
    c[2].metric("Answer match", f"{summary['answer_match']:.1f}%")
    c[3].metric("Source retrieval", f"{summary['source_retrieval']:.1f}%")
    c[4].metric("Citation correctness", f"{summary['citation_rate']:.1f}%")
    c = st.columns(5)
    c[0].metric("Groundedness", f"{summary['groundedness']:.1f}%")
    c[1].metric("Escalation accuracy", f"{summary['escalation_accuracy']:.1f}%")
    c[2].metric("High risk count", summary["high_risk_count"])
    c[3].metric("Average latency", f"{summary['avg_latency']:.0f} ms")
    c[4].metric("Total cost", f"${summary['total_cost']:.4f}")
    st.subheader(f"Launch readiness verdict: {summary['launch_readiness']}")
    st.info(charts.insight_summary(df, top_k=st.session_state.last_top_k))

    c1, c2 = st.columns(2)
    c1.plotly_chart(charts.prompt_comparison_chart(df), use_container_width=True)
    c2.plotly_chart(charts.category_score_chart(df), use_container_width=True)
    c1, c2 = st.columns(2)
    c1.plotly_chart(charts.failure_distribution_chart(df), use_container_width=True)
    c2.plotly_chart(charts.hallucination_distribution_chart(df), use_container_width=True)
    c1, c2 = st.columns(2)
    c1.plotly_chart(charts.latency_chart(df), use_container_width=True)
    c2.plotly_chart(charts.cost_chart(df), use_container_width=True)

    st.subheader("Failure table")
    cols = ["question", "category", "expected_source", "retrieved_sources_display", "actual_answer", "overall_score", "hallucination_risk", "failure_type", "suggested_fix"]
    st.dataframe(df[cols], hide_index=True, use_container_width=True)


def render_failure_analysis() -> None:
    st.title("Failure Analysis")
    df = charts.prepare_results(st.session_state.last_results)
    if df.empty:
        st.info("Run an evaluation to inspect failures.")
        return
    c1, c2, c3, c4, c5 = st.columns(5)
    category = c1.multiselect("Category", sorted(df["category"].unique()), default=sorted(df["category"].unique()))
    failure = c2.multiselect("Failure type", sorted(df["failure_type"].unique()), default=sorted(df["failure_type"].unique()))
    risk = c3.multiselect("Hallucination risk", sorted(df["hallucination_risk"].unique()), default=sorted(df["hallucination_risk"].unique()))
    prompt = c4.multiselect("Prompt", sorted(df["prompt_name"].unique()), default=sorted(df["prompt_name"].unique()))
    model = c5.multiselect("Model", sorted(df["model_name"].unique()), default=sorted(df["model_name"].unique()))
    filtered = df[
        df["category"].isin(category)
        & df["failure_type"].isin(failure)
        & df["hallucination_risk"].isin(risk)
        & df["prompt_name"].isin(prompt)
        & df["model_name"].isin(model)
    ]
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
    st.dataframe(filtered[table_cols], hide_index=True, use_container_width=True)
    st.download_button("Export filtered failures as CSV", filtered.to_csv(index=False), "ai_reliability_failures.csv", "text/csv")

    for _, row in filtered.head(50).iterrows():
        with st.expander(f"{row['failure_type']} | {row['question']}"):
            c1, c2 = st.columns(2)
            c1.markdown("**Expected answer**")
            c1.write(row["expected_answer"])
            c2.markdown("**Actual answer**")
            c2.write(row["actual_answer"])
            st.markdown("**Scoring breakdown**")
            st.json(
                {
                    "expected_answer_match_score": row["expected_answer_match_score"],
                    "source_retrieval_score": row["source_retrieval_score"],
                    "citation_correctness_score": row["citation_correctness_score"],
                    "groundedness_score": row["groundedness_score"],
                    "escalation_correctness_score": row["escalation_correctness_score"],
                    "hallucination_risk": row["hallucination_risk"],
                    "overall_score": row["overall_score"],
                }
            )
            st.markdown("**Retrieved chunks**")
            for chunk in parse_jsonish(row.get("retrieved_chunks")):
                st.caption(f"{chunk.get('source_name')} | {float(chunk.get('similarity', 0)):.2f}")
                render_plain_text(chunk.get("chunk_text", ""))
            st.markdown("**Final prompt used**")
            st.code(row.get("final_prompt", ""), language="text")


def render_prompt_comparison() -> None:
    st.title("Prompt Comparison")
    df = charts.prepare_results(st.session_state.last_results)
    if df.empty or df["prompt_name"].nunique() < 2:
        st.info("Run Current Prompt vs Improved Prompt mode to view prompt comparison.")
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


def render_settings_export() -> None:
    st.title("Settings / Export")
    st.subheader("API Key")
    st.caption("In-app keys are stored only in Streamlit session state. They are not saved to SQLite and are not written to files.")
    st.caption("Key priority: in-app key > Streamlit secrets > .env OPENAI_API_KEY > mock model fallback.")
    entered_key = st.text_input(
        "OpenAI API key",
        value=st.session_state.get("openai_api_key", ""),
        type="password",
        placeholder="sk-...",
        help="Priority: in-app key > Streamlit secrets > .env OPENAI_API_KEY > mock model fallback.",
    )
    st.session_state.openai_api_key = entered_key.strip()
    c1, c2, c3 = st.columns(3)
    c1.metric("Effective API key", api_key_status_label())
    c2.metric("Key source", api_key_source())
    c3.metric("Real LLM Mode", "Available" if effective_api_key() else "Unavailable")
    if st.session_state.openai_api_key:
        if st.button("Clear in-app API key"):
            st.session_state.openai_api_key = ""
            st.success("In-app API key cleared from this session.")
            st.rerun()
    if not effective_api_key():
        st.info("Mock Demo Mode is active. Real prompt/model evaluation requires an API key.")
    st.divider()

    c1, c2, c3 = st.columns(3)
    c1.metric("Streamlit secrets key", "Present" if streamlit_secret_api_key() else "Not present")
    c2.metric(".env OPENAI_API_KEY", "Present" if config.OPENAI_API_KEY else "Not present")
    c3.metric("Model A", config.OPENAI_MODEL_A)
    st.metric("Model B", config.OPENAI_MODEL_B)
    st.write(f"Database path: `{config.DATABASE_PATH}`")

    runs = database.eval_runs_df()
    if not runs.empty:
        st.subheader("Run history")
        st.dataframe(runs, hide_index=True, use_container_width=True)
    all_results = charts.prepare_results(database.all_results_df())
    if not all_results.empty:
        st.download_button("Export latest in-memory results as CSV", st.session_state.last_results.to_csv(index=False), "ai_reliability_latest_results.csv", "text/csv")
        st.download_button("Export all saved results as CSV", all_results.to_csv(index=False), "ai_reliability_all_results.csv", "text/csv")
    c1, c2 = st.columns(2)
    if c1.button("Clear evaluation results"):
        database.clear_results()
        st.session_state.last_results = pd.DataFrame()
        st.success("Evaluation results cleared.")
    if c2.button("Reset sample data"):
        load_demo()
        st.success("Sample data reset.")


def main() -> None:
    apply_theme()
    init_state()
    st.sidebar.title("AI Reliability Studio")
    st.sidebar.caption("Test, measure, improve, and safely escalate.")
    page = st.sidebar.radio(
        "Navigate",
        [
            "Overview",
            "Project Setup",
            "Knowledge Base",
            "System Prompt",
            "Evaluation Dataset",
            "Run Evaluation",
            "Results Dashboard",
            "Failure Analysis",
            "Prompt Comparison",
            "Settings / Export",
        ],
    )
    st.sidebar.divider()
    st.sidebar.write(f"Mode: {st.session_state.mode}")
    st.sidebar.write(f"Documents: {len(st.session_state.documents)}")
    st.sidebar.write(f"Chunks: {len(st.session_state.chunks)}")
    st.sidebar.write(f"Eval rows: {len(st.session_state.eval_df)}")

    pages = {
        "Overview": render_overview,
        "Project Setup": render_project_setup,
        "Knowledge Base": render_knowledge_base,
        "System Prompt": render_system_prompt,
        "Evaluation Dataset": render_eval_dataset,
        "Run Evaluation": render_run_evaluation,
        "Results Dashboard": render_results_dashboard,
        "Failure Analysis": render_failure_analysis,
        "Prompt Comparison": render_prompt_comparison,
        "Settings / Export": render_settings_export,
    }
    pages[page]()


if __name__ == "__main__":
    main()
