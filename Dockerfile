# syntax=docker/dockerfile:1

FROM --platform=linux/amd64 ghcr.io/astral-sh/uv:python3.10-bookworm

ARG DBOT_ARGS
ARG ENVIRONMENT=production
ARG COMMIT=""

RUN useradd --create-home avrae
USER avrae
WORKDIR /home/avrae

ENV GIT_COMMIT_SHA=${COMMIT}

COPY --chown=avrae:avrae pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY --chown=avrae:avrae . .

# Download AWS pubkey to connect to documentDB
RUN wget https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem

ENTRYPOINT uv run dbot.py $DBOT_ARGS