FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml .
RUN pip install --no-cache-dir -e . && pip install --no-cache-dir vosk
COPY pipeline/ pipeline/
EXPOSE 8000
CMD ["uvicorn", "pipeline.api:app", "--host", "0.0.0.0", "--port", "8000"]
