FROM python:3.12-slim

WORKDIR /app

COPY migrations /app/migrations

RUN pip install --no-cache-dir alembic>=1.13 sqlalchemy>=2.0 asyncpg>=0.29

CMD ["alembic", "-c", "migrations/alembic.ini", "upgrade", "head"]
