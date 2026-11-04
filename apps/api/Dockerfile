# GigScout API. Build: docker build -t gigscout-api apps/api
FROM python:3.12-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /usr/local/bin/uv

WORKDIR /app
# dependencies first, so code changes do not reinstall them
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY profiles ./profiles
RUN uv sync --frozen --no-dev

# leads, the vector store and the embedding model live on a volume; the app never runs as root
RUN useradd --system --uid 10001 --home-dir /data gigscout && mkdir -p /data && chown gigscout /data
USER gigscout
ENV PATH="/app/.venv/bin:$PATH" \
    GIGSCOUT_DATA_DIR=/data \
    FASTEMBED_CACHE_PATH=/data/models \
    GIGSCOUT_MLFLOW_ENABLED=false

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["gigscout", "serve", "--host", "0.0.0.0", "--port", "8000"]
