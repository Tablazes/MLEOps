# Eén image voor zowel cloud (Render) als edge (Docker op edge-node).
# Runtime-deps staan inline (bewust geen aparte requirements-file): alleen wat
# serve.py nodig heeft, zodat de image klein blijft en snel bouwt.
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir scikit-learn==1.5.2 numpy==1.26.4 \
    fastapi==0.115.0 uvicorn==0.34.0 pydantic==2.9.2

COPY serve.py ./
COPY models/sentiment_heavy.pkl ./models/

# Niet als root draaien: de service heeft alleen leesrechten op /app nodig.
RUN useradd --no-create-home vitacall && chown -R vitacall /app
USER vitacall

ENV MODEL_PATH=/app/models/sentiment_heavy.pkl
# Render injecteert $PORT; lokaal/edge valt het terug op 8000.
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\",\"8000\")}/health', timeout=3)"

# Shell-form zodat $PORT geëxpandeerd wordt.
CMD uvicorn serve:app --host 0.0.0.0 --port ${PORT:-8000}
