# Eén image voor zowel cloud (Render) als edge (Docker op edge-node).
# Slank gehouden via requirements-deploy.txt (alleen runtime-deps).
FROM python:3.11-slim

WORKDIR /app

# Eerst alleen de requirements kopiëren -> betere layer-cache bij code-changes.
COPY requirements-deploy.txt ./
RUN pip install --no-cache-dir -r requirements-deploy.txt

COPY serve.py ./
COPY models/sentiment_heavy.pkl ./models/

ENV MODEL_PATH=/app/models/sentiment_heavy.pkl
# Render injecteert $PORT; lokaal/edge valt het terug op 8000.
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\",\"8000\")}/health', timeout=3)"

# Shell-form zodat $PORT geëxpandeerd wordt.
CMD uvicorn serve:app --host 0.0.0.0 --port ${PORT:-8000}
