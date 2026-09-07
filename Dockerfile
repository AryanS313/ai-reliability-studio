FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    AUTH_MODE=public-session \
    APP_ENV=public-demo \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_HEADLESS=true

WORKDIR /app
COPY requirements.txt requirements-lock.txt ./
RUN python -m pip install --no-cache-dir --only-binary=:all: -c requirements-lock.txt -r requirements.txt \
    && useradd --create-home --uid 10001 studio

# Copy only the runtime inputs; never copy a developer's .env, database, or credentials.
COPY --chown=studio:studio app.py ./
COPY --chown=studio:studio .streamlit/config.toml ./.streamlit/config.toml
COPY --chown=studio:studio src/ ./src/
COPY --chown=studio:studio data/sample_docs/ ./data/sample_docs/
COPY --chown=studio:studio examples/ ./examples/
COPY --chown=studio:studio prompts/ ./prompts/
COPY --chown=studio:studio migrations/ ./migrations/
USER studio
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4)"
CMD ["python", "-m", "streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
