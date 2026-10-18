FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts
COPY alembic.ini .

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
# Migrate, seed the demo data only if the database is empty, then serve. Render supplies PORT.
CMD ["sh", "-c", "python -m scripts.migrate_and_seed --if-empty && exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]
