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
# --no-root allows us to install dependencies without having the project code yet
RUN uv sync --frozen --no-install-project --no-dev

# Stage 2: Production stage
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app"

WORKDIR /app/auth

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy common modules and auth app code
# Assuming context is project root according to docker-compose.yml
COPY common/ /app/common/
COPY auth/ /app/auth/

RUN chmod +x /app/auth/entrypoint.sh

# Expose port
EXPOSE 8000

# Run the application
ENTRYPOINT ["/app/auth/entrypoint.sh"]
