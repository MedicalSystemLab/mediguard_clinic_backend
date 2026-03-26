#!/bin/bash
set -e

# FastAPI 서버 실행
echo "Starting FastAPI application..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
