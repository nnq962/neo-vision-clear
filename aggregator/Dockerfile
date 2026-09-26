# syntax=docker/dockerfile:1.7

FROM python:3.11-slim-bookworm

ARG UV_VERSION=0.12.16

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    AGGREGATOR_HOST=0.0.0.0 \
    AGGREGATOR_PORT=8100 \
    AGGREGATOR_SOURCE_STALE_SECONDS=3 \
    AGGREGATOR_CONFIG_PATH=/app/config/config.json

WORKDIR /app

RUN python -m pip install "uv==${UV_VERSION}"

COPY pyproject.toml uv.lock README.md ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY config/config.json ./config/config.json

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
    && useradd --create-home --uid 10001 aggregator \
    && chown -R aggregator:aggregator /app

USER aggregator

EXPOSE 8100

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/health', timeout=2)" || exit 1

CMD ["aggregator-server"]
