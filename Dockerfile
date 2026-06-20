FROM python:3.11-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN python -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

COPY . /app

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir /app

FROM python:3.11-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV APP_MODULE=app.main:app
ENV PORT=8000
ENV PATH="/opt/venv/bin:$PATH"

RUN groupadd --system --gid 1001 appuser \
    && useradd --system --uid 1001 --gid 1001 --create-home --home-dir /home/appuser appuser

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

RUN chown -R appuser:appuser /app /opt/venv

USER appuser

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn ${APP_MODULE} --host 0.0.0.0 --port ${PORT}"]
