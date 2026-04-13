# Stage 1: Build stage
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-install-project --no-dev

# Stage 2: Production stage
FROM python:3.12-slim

# Install curl for healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app"

WORKDIR /app/consumer

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy common modules and consumer app code
COPY common/ /app/common/
COPY clinical_manage/app/models/ /app/clinical_manage/app/models/
COPY consumer/ /app/consumer/
COPY auth/ /app/auth
COPY biosignal/ /app/biosignal

RUN chmod +rx /app/consumer/entrypoint.sh

# Run the consumer service
ENTRYPOINT ["/app/consumer/entrypoint.sh"]
