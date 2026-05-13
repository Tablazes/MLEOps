"""Embedded FastAPI backend — gestart als daemon-thread door ui.py."""
from __future__ import annotations

import logging
import pickle
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("vitacall")

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


def _kw_server(text: str) -> list[dict]:
    t = text.lower()
    return [{"text": kw, "type": kt} for kt, kws in KEYWORDS_NL.items() for kw in kws if kw in t]


@dataclass
class _Metrics:
    requests_total: int = 0
    requests_errors: int = 0
    latencies_ms: deque = field(default_factory=lambda: deque(maxlen=200))
    confidences: deque = field(default_factory=lambda: deque(maxlen=100))
    started_at: float = field(default_factory=time.time)

    def record(self, latency_ms: float, error: bool = False) -> None:
        self.requests_total += 1
        if error:
            self.requests_errors += 1
        self.latencies_ms.append(latency_ms)

    def snapshot(self) -> dict:
        n = len(self.latencies_ms)
        s = sorted(self.latencies_ms) if n else [0]
        return {
            "uptime_s": round(time.time() - self.started_at, 1),
            "requests_total": self.requests_total,
            "requests_errors": self.requests_errors,
            "error_rate": round(self.requests_errors / max(self.requests_total, 1), 4),
            "p50_ms": round(s[n // 2], 2) if n else 0,
            "p95_ms": round(s[int(n * 0.95)], 2) if n else 0,
            "avg_confidence": round(sum(self.confidences) / len(self.confidences), 3) if self.confidences else 0.0,
        }


@dataclass
class _Drift:
    window: deque = field(default_factory=lambda: deque(maxlen=100))
    threshold: float = 0.30
    min_samples: int = 10

    def add(self, label: str) -> None:
        self.window.append(1 if label == "positief" else 0)

    def snapshot(self) -> dict:
        n = len(self.window)
        if n < self.min_samples:
            return {"status": "onvoldoende_data", "positive_rate": 0.0, "drift_score": 0.0, "samples": n}
        pos_rate = sum(self.window) / n
        score = abs(pos_rate - 0.5)
        return {"status": "drift" if score > self.threshold else "normaal",
                "positive_rate": round(pos_rate, 3), "drift_score": round(score, 3), "samples": n}


try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field as PField
    import uvicorn

    class AnalyzeReq(BaseModel):
        text: str = PField(..., min_length=1, max_length=10_000)

    _FASTAPI_OK = True
except ImportError:
    _FASTAPI_OK = False


def start_api_server(heavy_model_path: Path, api_url: str) -> None:
    """Load heavy model + start uvicorn in daemon thread. No-op if pkl missing."""
    if not heavy_model_path.exists():
        log.warning("heavy model niet gevonden (%s), backend niet gestart", heavy_model_path)
        return
    if not _FASTAPI_OK:
        log.warning("fastapi/uvicorn niet beschikbaar, backend niet gestart")
        return

    with open(heavy_model_path, "rb") as fh:
        _model = pickle.load(fh)

    _metrics = _Metrics()
    _drift = _Drift()

    api = FastAPI(title="VitaCall API", version="2.0.0")
    api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])

    @api.get("/health")
    def health():  # noqa: ANN201
        return {"status": "healthy", "model_loaded": True}

    @api.post("/analyze")
    def analyze(req: AnalyzeReq):  # noqa: ANN201
        t0 = time.perf_counter()
        err = False
        try:
            proba = _model.predict_proba([req.text])[0]
            label_int = _model.classes_[proba.argmax()]
            sentiment = "positief" if label_int == 1 else "negatief"
            confidence = round(float(proba.max()), 3)
            _drift.add(sentiment)
            _metrics.confidences.append(confidence)
            return {"sentiment": sentiment, "confidence": confidence, "keywords": _kw_server(req.text)}
        except Exception:
            err = True
            raise HTTPException(status_code=500, detail="Interne fout")
        finally:
            _metrics.record((time.perf_counter() - t0) * 1000, error=err)

    @api.get("/drift")
    def drift_ep():  # noqa: ANN201
        return _drift.snapshot()

    @api.get("/metrics")
    def metrics_ep():  # noqa: ANN201
        return _metrics.snapshot()

    threading.Thread(target=lambda: uvicorn.run(api, host="127.0.0.1", port=8000, log_level="warning"),
                     daemon=True).start()
    log.warning("API backend gestart op %s", api_url)
