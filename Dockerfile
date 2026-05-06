FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    scikit-learn==1.5.2 \
    pandas==2.2.3 \
    numpy==1.26.4 \
    fastapi==0.115.0 \
    uvicorn==0.34.0 \
    pyarrow==17.0.0 \
    requests==2.32.3 \
    pydantic==2.9.2

COPY serve.py ./
COPY models/sentiment_heavy.pkl ./models/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)"

CMD ["uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8000"]
