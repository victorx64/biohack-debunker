FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml /app/
COPY README.md /app/
COPY src /app/src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1

EXPOSE 8001

CMD ["uvicorn", "transcription_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
