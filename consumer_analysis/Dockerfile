# Stage 1: Build stage
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install build dependencies for RocksDB
RUN apt-get update && apt-get install -y \
    build-essential \
    librocksdb-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-install-project --no-dev

# Stage 2: Production stage
FROM python:3.12-slim

# Install curl for healthcheck and RocksDB runtime library
RUN apt-get update && apt-get install -y \
    curl \
    librocksdb-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app"

WORKDIR /app/consumer_analysis

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy common modules and consumer_analysis app code
COPY common/ /app/common/
COPY consumer_analysis/ /app/consumer_analysis/

RUN chmod +rx /app/consumer_analysis/entrypoint.sh

# Run the analysis consumer service
ENTRYPOINT ["/app/consumer_analysis/entrypoint.sh"]
