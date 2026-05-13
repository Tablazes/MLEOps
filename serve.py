"""Productie-entry voor de FastAPI-service.

Identieke logica als de cellen 4.x in main.ipynb, maar zonder Jupyter.
Run: uvicorn serve:app --host 0.0.0.0 --port 8000
"""
import json
import logging
import os
import pickle
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

log = logging.getLogger("vitacall")
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

MODEL_PATH = os.environ.get("MODEL_PATH", "models/sentiment_heavy.pkl")

with open(MODEL_PATH, "rb") as f:
    model = pickle.load(f)
log.info("Model geladen uit %s", MODEL_PATH)


KEYWORDS_NL = {
    "urgentie": [
        "pijn op de borst", "borstpijn", "benauwd", "bewusteloos",
        "flauwgevallen", "bloeding", "hartaanval", "herseninfarct",
        "beroerte", "overdosis", "niet ademen", "koorts", "gevallen",
    ],
    "medicatie": [
        "paracetamol", "ibuprofen", "insuline", "antibiotica",
        "bloedverdunner", "bloeddruk", "inhalator", "epipen",
    ],
}


def find_keywords(text: str):
    t = text.lower()
    return [{"text": kw, "type": ktype}
            for ktype, kws in KEYWORDS_NL.items()
            for kw in kws if kw in t]


def predict_sentiment(text: str):
    proba = model.predict_proba([text])[0]
    label_int = model.classes_[proba.argmax()]
    return ("positief" if label_int == 1 else "negatief"), round(float(proba.max()), 3)


@dataclass
class Metrics:
    requests_total: int = 0
    requests_errors: int = 0
    latencies_ms: deque = field(default_factory=lambda: deque(maxlen=200))
    confidences: deque = field(default_factory=lambda: deque(maxlen=100))
    started_at: float = field(default_factory=time.time)

    def record_request(self, latency_ms, error=False):
        self.requests_total += 1
        if error:
            self.requests_errors += 1
        self.latencies_ms.append(latency_ms)

    def record_prediction(self, label, confidence):
        self.confidences.append(confidence)

    def snapshot(self):
        n = len(self.latencies_ms)
        s = sorted(self.latencies_ms) if n else [0]
        return {
            "uptime_s":        round(time.time() - self.started_at, 1),
            "requests_total":  self.requests_total,
            "requests_errors": self.requests_errors,
            "error_rate":      round(self.requests_errors / max(self.requests_total, 1), 4),
            "p50_ms":          round(s[n // 2], 2) if n else 0,
            "p95_ms":          round(s[int(n * 0.95)], 2) if n else 0,
            "avg_confidence":  round(sum(self.confidences) / len(self.confidences), 3) if self.confidences else 0.0,
        }


@dataclass
class DriftDetector:
    window: deque = field(default_factory=lambda: deque(maxlen=100))
    threshold: float = 0.30
    min_samples: int = 10

    def add(self, label):
        self.window.append(1 if label == "positief" else 0)

    def snapshot(self):
        n = len(self.window)
        if n < self.min_samples:
            return {"status": "onvoldoende_data", "positive_rate": 0.0,
                    "drift_score": 0.0, "samples": n}
        pos_rate = sum(self.window) / n
        score = abs(pos_rate - 0.5)
        status = "drift" if score > self.threshold else "normaal"
        if status == "drift":
            log.warning("DRIFT alert: positive_rate=%.3f score=%.3f n=%d", pos_rate, score, n)
        return {"status": status, "positive_rate": round(pos_rate, 3),
                "drift_score": round(score, 3), "samples": n}


metrics = Metrics()
drift = DriftDetector()


class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10_000)


class AnalyzeResponse(BaseModel):
    sentiment: str
    confidence: float
    keywords: list


app = FastAPI(title="VitaCall API", version="2.0.0")

# CORS open voor lokale PySide6 desktop-app. In productie zou je dit
# beperken tot het exacte origin van de frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "healthy", "model_loaded": model is not None}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    t0 = time.perf_counter()
    err = False
    try:
        sentiment, confidence = predict_sentiment(req.text)
        drift.add(sentiment)
        metrics.record_prediction(sentiment, confidence)
        return AnalyzeResponse(sentiment=sentiment, confidence=confidence,
                               keywords=find_keywords(req.text))
    except Exception:
        err = True
        raise HTTPException(status_code=500, detail="Interne fout bij scoring")
    finally:
        metrics.record_request((time.perf_counter() - t0) * 1000, error=err)


@app.get("/drift")
def drift_endpoint():
    return drift.snapshot()


@app.get("/metrics")
def metrics_endpoint():
    return metrics.snapshot()
