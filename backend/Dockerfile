# Build context is the repo root (see docker-compose.yml / `docker build -f backend/Dockerfile .`)
# so paths below are relative to the repo root, not this file's directory.
FROM python:3.12-slim

WORKDIR /app

COPY backend/pyproject.toml ./pyproject.toml
COPY backend/app ./app

RUN pip install --no-cache-dir -e .

EXPOSE 8000

# --reload is fine here: this image is for local dev via docker-compose, not production.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
