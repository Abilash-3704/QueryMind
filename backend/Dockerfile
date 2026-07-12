# Build context is the repo root (see docker-compose.yml / `docker build -f backend/Dockerfile .`)
# so paths below are relative to the repo root, not this file's directory.
FROM python:3.12-slim

WORKDIR /app

COPY backend/pyproject.toml ./pyproject.toml
COPY backend/app ./app

RUN pip install --no-cache-dir -e .

EXPOSE 8000

# Shell form (not exec-form array) so $PORT actually expands — cloud hosts like Render
# assign their own port via this env var; falls back to 8000 for local docker-compose use.
# --reload is harmless in production (just an inert file watcher once the image is built).
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --reload
