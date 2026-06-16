FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV APP_MODULE=app.main:app
ENV PORT=8000

COPY . /app

RUN pip install --no-cache-dir -e /app

CMD ["sh", "-c", "alembic upgrade head && uvicorn ${APP_MODULE} --host 0.0.0.0 --port ${PORT}"]
