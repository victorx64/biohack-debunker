FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml /app/
COPY src /app/src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1

EXPOSE 8003

CMD ["uvicorn", "research_service.main:app", "--host", "0.0.0.0", "--port", "8003"]
