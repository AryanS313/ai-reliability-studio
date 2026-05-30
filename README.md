# AI Reliability Studio

A local-first QA and benchmarking dashboard for testing LLM assistants before launch.

## Problem

AI assistants are easy to prototype but hard to trust. Teams need scalable testing to evaluate correctness, grounding, hallucination risk, escalation behavior, cost, and latency across many expected-answer cases before they ship an assistant to customers.

AI Reliability Studio answers:

> Our AI assistant exists, but is it accurate, grounded, safe, and reliable enough to ship?

## Product Flow

1. Load the sample FinSure demo or upload custom data.
2. Add company documents.
3. Paste the current system prompt.
4. Select a model.
5. Upload an expected-answer test dataset.
6. Run evaluation.
7. View the reliability dashboard.
8. Compare the improved prompt.
9. Analyze failures and suggested fixes.
10. Export results.

## Key Features

- Demo Mode with fictional FinSure fintech data
- Custom Upload Mode for user documents and evaluation CSVs
- Current system prompt testing
- Rule-generated improved prompt comparison
- RAG-style TF-IDF document retrieval
- Expected-answer evaluation
- Source retrieval and citation checking
- Groundedness scoring
- Hallucination risk scoring
- Escalation behavior testing
- Cost and latency tracking
- Launch readiness verdict
- Failure analysis with suggested fixes
- CSV export
- Mock model fallback when no API key is present
- Optional OpenAI model calls when configured

## How to Run

macOS/Linux:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Windows:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

If your machine exposes Python as `python3`, use:

```bash
python3 -m streamlit run app.py
```

## Deploy on Streamlit Community Cloud

This repository is ready for Streamlit Community Cloud:

- `app.py` is at the project root.
- `requirements.txt` contains the external Python dependencies.
- The app works without secrets by using Mock Demo Mode.
- Sample documents, prompts, and evaluation data load from relative project paths under `data/` and `prompts/`.

Deployment steps:

1. Push this repository to GitHub.
2. Go to [Streamlit Community Cloud](https://streamlit.io/cloud).
3. Create a new app from the GitHub repo.
4. Set the main file path to `app.py`.
5. Deploy.

No API key is required for the public demo. The app will default to Mock Demo Mode.

## How Recruiters Can Test This

1. Open the deployed Streamlit link.
2. Click `Load Sample Fintech Demo`.
3. Go to `Run Evaluation`.
4. Select `Current Prompt vs Improved Prompt`.
5. Keep `mock-model` selected.
6. Click `Run Evaluation`.
7. View `Results Dashboard`.
8. Open `Failure Analysis` to inspect failed test cases.
9. Open `Prompt Comparison` to see whether the improved system prompt performed better.

## Real LLM Mode

Real LLM Mode can be enabled in two ways:

1. Paste an OpenAI API key into the masked field on the Settings / Export page. This is stored only in Streamlit `session_state`; it is not written to SQLite or files.
2. Configure Streamlit secrets for deployment:

```toml
OPENAI_API_KEY = "sk-..."
```

In Streamlit Community Cloud, add this in the app's `Settings -> Secrets` panel. Do not commit local `.streamlit/secrets.toml`.

For local development, you can also create a `.env` file:

```text
OPENAI_API_KEY=
OPENAI_MODEL_A=gpt-4o-mini
OPENAI_MODEL_B=gpt-4.1-mini
```

Key priority is: in-app session key, then Streamlit secrets, then `.env` key, then mock model fallback. Without an API key, the app defaults to Mock Demo Mode and uses a deterministic mock model. The mock model is intentionally designed so the improved prompt performs better on citations, escalation, and unsupported-answer handling.

## Evaluation Dataset Format

CSV columns:

```csv
question,expected_answer,expected_source,category,should_escalate
```

`should_escalate` accepts values such as `true`, `false`, `yes`, `no`, `1`, and `0`.

## Metrics

- **Expected answer match**: keyword overlap between expected answer and actual answer.
- **Source retrieval**: whether the expected source was retrieved.
- **Citation correctness**: whether the actual answer cites the expected source.
- **Groundedness**: source retrieval, citation, and retrieved-context overlap.
- **Escalation correctness**: whether the assistant escalated when expected.
- **Hallucination risk**: Low, Medium, or High based on missing sources, unsupported definitive claims, poor answer match, failed escalation, and out-of-scope handling.
- **Overall reliability**: weighted score combining answer match, retrieval, citation, groundedness, and escalation.

## Launch Readiness

The dashboard labels a run as:

- **Ready for Controlled Beta** when overall reliability, citation correctness, escalation accuracy, and hallucination risk meet launch thresholds.
- **Needs Improvement** when scores are mixed or one major metric is weak.
- **Not Ready for Launch** when reliability is low, hallucination risk is high, or escalation accuracy is unsafe.

## Portfolio Explanation

This project demonstrates AI product management beyond chatbot creation:

- evaluation design
- expected-answer testing
- system prompt evaluation
- hallucination-risk tracking
- citation correctness
- escalation testing
- launch-readiness metrics
- failure diagnosis
- cost-quality tradeoff analysis

## Roadmap

Future versions could add direct testing against external chatbot APIs, scheduled regression runs, human reviewer workflows, dataset versioning, richer semantic similarity metrics, and authenticated team workspaces. V1 intentionally stays local-first and simple.

## Product Principle

An AI assistant is not ready just because it can answer. It is ready only when its answers can be tested, measured, trusted, improved, and safely escalated at scale.
