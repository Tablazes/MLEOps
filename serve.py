"""VitaCall service-laag: single source of truth voor de cloud-API.

Eén module die zowel het notebook als de productie-container gebruikt, zodat de
service-logica (keywords, monitoring, drift, Prometheus-export, FastAPI-app) op
exact één plek staat. Geen duplicatie tussen `main.ipynb` en deze file.

- Notebook: importeert `build_app`, `Metrics`, `DriftDetector`,
  `to_prometheus_exposition` en geeft het in-memory getrainde model door.
- Container (Dockerfile / Render): importeert `app` hieronder, dat het model uit
  `MODEL_PATH` laadt. Start met `uvicorn serve:app --host 0.0.0.0 --port 8000`.
"""
import logging
import os
import pickle
import time
from collections import deque
from dataclasses import dataclass, field

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

log = logging.getLogger("vitacall")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

MODEL_PATH = os.environ.get("MODEL_PATH", "models/sentiment_heavy.pkl")


# --------------------------------------------------------------------------- #
# Domein-keywords (zorg-context)
# --------------------------------------------------------------------------- #
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
    """Zoek domein-keywords voor highlighting in de output."""
    t = text.lower()
    return [{"text": kw, "type": ktype}
            for ktype, kws in KEYWORDS_NL.items()
            for kw in kws if kw in t]


def predict_sentiment(model, text: str):
    """Wrapper rond model.predict_proba die een leesbaar label teruggeeft."""
    proba = model.predict_proba([text])[0]
    label_int = model.classes_[proba.argmax()]
    return ("positief" if label_int == 1 else "negatief"), round(float(proba.max()), 3)


# --------------------------------------------------------------------------- #
# Monitoring: Metrics + DriftDetector (ook gebruikt door notebook-sectie 4)
# --------------------------------------------------------------------------- #
@dataclass
class Metrics:
    """System- + model-counters. Een deque met maxlen werkt als ringbuffer:
    oude metingen vallen er vanzelf uit."""
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
        # Voor avg-confidence in de snapshot; handig om model-rot vroeg te zien.
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
    """Output-distributie drift: hoever wijkt de positieve-rate af van 0.5."""
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


def to_prometheus_exposition(metrics_snapshot: dict, drift_snapshot: dict) -> str:
    """Zet metrics+drift om naar Prometheus exposition-format (text/plain).

    Eén HELP/TYPE/value-blok per metric, zodat een Prometheus-server dit kan
    scrapen op /metrics-prom (zie monitoring/prometheus.yml).
    """
    lines = []

    def m(name, help_text, mtype, val):
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {mtype}")
        lines.append(f"{name} {val}")

    m("vitacall_uptime_seconds", "Process uptime", "gauge", metrics_snapshot.get("uptime_s", 0))
    m("vitacall_requests_total", "Total HTTP requests", "counter", metrics_snapshot.get("requests_total", 0))
    m("vitacall_requests_errors_total", "Total errored requests", "counter", metrics_snapshot.get("requests_errors", 0))
    m("vitacall_latency_p50_ms", "p50 request latency in ms", "gauge", metrics_snapshot.get("p50_ms", 0))
    m("vitacall_latency_p95_ms", "p95 request latency in ms", "gauge", metrics_snapshot.get("p95_ms", 0))
    m("vitacall_avg_confidence", "Mean prediction confidence", "gauge", metrics_snapshot.get("avg_confidence", 0))
    m("vitacall_drift_score", "Output-distribution drift score", "gauge", drift_snapshot.get("drift_score", 0))
    m("vitacall_drift_samples", "Samples in drift window", "gauge", drift_snapshot.get("samples", 0))
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Request/response-contract
# --------------------------------------------------------------------------- #
class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10_000)


class AnalyzeResponse(BaseModel):
    sentiment: str
    confidence: float
    keywords: list


def build_app(model, *, metrics: "Metrics | None" = None,
              drift: "DriftDetector | None" = None) -> FastAPI:
    """Bouw de FastAPI-app rond een geladen model.

    Het notebook geeft hier het in-memory getrainde model door; de container
    geeft het uit MODEL_PATH geladen model door. Eén app-definitie voor beide.
    De gebruikte Metrics/DriftDetector-instanties worden teruggehangen op
    `app.state` zodat aanroepers (notebook-sectie 4) de live snapshots kunnen
    uitlezen.
    """
    metrics = metrics or Metrics()
    drift = drift or DriftDetector()

    app = FastAPI(title="VitaCall API", version="2.0.0")
    app.state.metrics = metrics
    app.state.drift = drift

    # CORS open zodat een externe edge-client of dashboard de API mag bevragen.
    # In productie beperk je dit tot het exacte origin van de consument.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/")
    def root():
        # Nette landingsroute i.p.v. een kale 404 op de root.
        return {"service": "VitaCall API", "status": "ok",
                "endpoints": ["/health", "/analyze", "/drift", "/metrics", "/metrics-prom"]}

    @app.get("/health")
    def health():
        # Deploy-bewijs: Render injecteert RENDER_GIT_COMMIT, zodat het notebook
        # kan verifiëren dat de live service exact deze repo-commit draait.
        return {"status": "healthy", "model_loaded": model is not None,
                "commit": os.environ.get("RENDER_GIT_COMMIT", "lokaal")[:12],
                "on_render": bool(os.environ.get("RENDER"))}

    @app.post("/analyze", response_model=AnalyzeResponse)
    def analyze(req: AnalyzeRequest):
        t0 = time.perf_counter()
        err = False
        try:
            sentiment, confidence = predict_sentiment(model, req.text)
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

    @app.get("/metrics-prom")
    def metrics_prom():
        """Prometheus scrape-endpoint (text/plain exposition-format)."""
        return PlainTextResponse(to_prometheus_exposition(metrics.snapshot(), drift.snapshot()))

    return app


def _load_model(path: str):
    with open(path, "rb") as f:
        m = pickle.load(f)
    log.info("Model geladen uit %s", path)
    return m


# Container-entry: laadt het model uit MODEL_PATH en bouwt de app.
# Het notebook gebruikt build_app() rechtstreeks en raakt dit niet aan.
app = build_app(_load_model(MODEL_PATH)) if os.path.exists(MODEL_PATH) else None
