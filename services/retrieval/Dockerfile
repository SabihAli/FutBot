FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
COPY packages/futbot-common packages/futbot-common
RUN pip install --no-cache-dir -r requirements.txt

COPY services/retrieval services/retrieval
COPY services/__init__.py services/__init__.py
COPY src/ingestion/chunking src/ingestion/chunking
COPY src/__init__.py src/__init__.py
COPY src/ingestion/__init__.py src/ingestion/__init__.py

ENV PYTHONPATH=/app
CMD ["uvicorn", "services.retrieval.main:app", "--host", "0.0.0.0", "--port", "8085"]
