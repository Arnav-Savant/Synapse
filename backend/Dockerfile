# backend/Dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml poetry.lock* ./
RUN pip install --no-cache-dir poetry && poetry config virtualenvs.create false \
    && poetry install --no-root --only main

COPY . .

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host ${APP_HOST:-127.0.0.1} --port ${APP_PORT:-8000}"]
