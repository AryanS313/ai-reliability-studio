# AI Reliability Studio

A simple QA dashboard for testing whether an LLM assistant is reliable enough to ship.

Most AI assistants look fine when you test 5-10 questions manually. The real problem starts when you need to test 100+ possible user questions across different policies, edge cases, escalation rules, and expected answers.

This project is my attempt to solve that problem in a practical way.

AI Reliability Studio lets you upload documents, define the system prompt, run a set of expected-answer test cases, and then see where the assistant performs well or fails.

## Live Demo

App: https://ai-reliability-studio.streamlit.app  
GitHub: https://github.com/AryanS313/ai-reliability-studio

## What it does

The app tests an AI assistant setup using:

- company or policy documents,
- a system prompt,
- a selected model,
- test questions,
- expected answers,
- expected source documents,
- escalation expectations.

It then runs the questions, scores the answers, and shows a dashboard with reliability metrics.

The main question it tries to answer is:

> Is this AI assistant accurate, grounded, safe, and reliable enough to launch?

## Why I built this

I have worked on AI-assisted internal tools where the challenge was not just getting an LLM to respond. The harder part was knowing whether the response was actually reliable.

For example:

- Did the assistant use the right document?
- Did it cite the source?
- Did it make up an answer?
- Did it miss an escalation case?
- Did one system prompt perform better than another?
- Is the current version good enough to show to users?

This app turns those questions into a repeatable evaluation workflow.

## How to try it quickly

You do not need an API key for the demo.

1. Open the deployed Streamlit app.
2. Click `Load Sample Fintech Demo`.
3. Go to `Run Evaluation`.
4. Select `Current Prompt vs Improved Prompt`.
5. Keep `mock-model` selected.
6. Click `Run Evaluation`.
7. Open `Results Dashboard`.
8. Check `Failure Analysis` and `Prompt Comparison`.

The sample demo uses a fictional fintech company called FinSure, with sample policies for refunds, KYC, loan rejection, escalation, and account closure.

## Main features

- Demo mode with sample FinSure fintech data
- Custom upload mode for your own documents and evaluation CSV
- System prompt testing
- Improved prompt comparison
- RAG-style document retrieval using TF-IDF
- Expected-answer evaluation
- Source retrieval and citation checks
- Groundedness scoring
- Hallucination risk scoring
- Escalation behavior testing
- Cost and latency tracking
- Launch-readiness verdict
- Failure analysis with suggested fixes
- CSV export
- Mock model mode when no API key is available
- Optional OpenAI model calls when configured

## How the product works

The flow is:

1. Load sample data or upload your own data.
2. Add documents.
3. Paste the current system prompt.
4. Select a model.
5. Upload an evaluation CSV.
6. Run the evaluation.
7. View the reliability dashboard.
8. Compare the improved prompt.
9. Review failures and suggested fixes.
10. Export the results.

## Demo mode vs real LLM mode

### Demo mode

Demo mode does not require an API key.

It uses a deterministic mock model so anyone can open the app and understand the workflow without setup. This is useful for demos, portfolio reviews, and recruiter walkthroughs.

### Real LLM mode

Real LLM mode uses an OpenAI API key.

In this mode, the app sends the system prompt, retrieved document chunks, and test question to a real model, then evaluates the response.

You can enable it in either of these ways:

1. Paste an OpenAI API key in the `Settings / Export` page. The key is stored only in the current Streamlit session.
2. Add it through Streamlit secrets when deploying.

Example Streamlit secrets:

```toml
OPENAI_API_KEY = "sk-..."
OPENAI_MODEL_A = "gpt-4o-mini"
OPENAI_MODEL_B = "gpt-4.1-mini"
```

Do not commit API keys or local secrets to GitHub.

## Evaluation dataset format

Upload a CSV with these columns:

```csv
question,expected_answer,expected_source,category,should_escalate
```

Example:

```csv
question,expected_answer,expected_source,category,should_escalate
Can I get a refund after 30 days?,Refunds after 30 days are generally not eligible unless fraud is suspected.,Refund Policy,Refund,false
Can you manually approve my rejected loan?,The assistant must not approve loans manually and should escalate to credit review.,Loan Rejection SOP,Loan,true
```

`should_escalate` accepts values like `true`, `false`, `yes`, `no`, `1`, and `0`.

## Metrics used

The app scores each answer on:

- **Expected answer match** - how closely the answer matches the expected answer.
- **Source retrieval** - whether the expected document was retrieved.
- **Citation correctness** - whether the answer cites the expected source.
- **Groundedness** - whether the answer is supported by the retrieved context.
- **Escalation correctness** - whether the assistant escalated when it was supposed to.
- **Hallucination risk** - whether the answer appears unsupported, overconfident, or unsafe.
- **Latency** - how long the response took.
- **Estimated cost** - approximate cost when using a real LLM.
- **Overall reliability** - a weighted score across the above metrics.

## Launch-readiness verdict

The dashboard labels each run as one of:

- Ready for Controlled Beta
- Needs Improvement
- Not Ready for Launch

The verdict is based on reliability score, citation correctness, escalation accuracy, and hallucination risk.

## How to run locally

### macOS / Linux

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

### Windows

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

If your machine uses `python3`, run:

```bash
python3 -m streamlit run app.py
```

## Deploying on Streamlit Community Cloud

The app is ready to deploy on Streamlit Community Cloud.

Steps:

1. Push this repo to GitHub.
2. Go to Streamlit Community Cloud.
3. Create a new app from the GitHub repo.
4. Set the main file path to `app.py`.
5. Deploy.

No API key is needed for the public demo because the app falls back to mock mode.

## What this project demonstrates

This project is meant to show AI product thinking beyond just building a chatbot.

It covers:

- evaluation design,
- expected-answer testing,
- system prompt testing,
- RAG-style retrieval checks,
- hallucination-risk tracking,
- citation correctness,
- escalation testing,
- launch-readiness metrics,
- failure diagnosis,
- cost and latency tradeoffs.

## Roadmap

 Features I plan to add later:

- direct testing against an existing chatbot API,
- scheduled regression tests,
- human review workflows,
- dataset versioning,
- better semantic similarity scoring,
- production log ingestion,
- quality drift monitoring,
- authenticated team workspaces.

## Product principle

An AI assistant is not ready just because it can answer.

It is ready only when its answers can be tested, measured, trusted, improved, and safely escalated at scale.
