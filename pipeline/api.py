"""VitaCall API — sentiment & keyword analyse + drift monitoring."""
import os
import pickle
from collections import deque
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

KEYWORDS: dict[str, list[str]] = {
    "urgentie": [
        "pijn op de borst", "borst", "borstpijn", "druk op de borst",
        "ademhalingsmoeilijkheden", "benauwd", "benauwdheid",
        "bewusteloos", "niet aanspreekbaar", "flauwgevallen",
        "bloed", "bloeding", "veel bloed",
        "hartaanval", "hartkloppingen", "hartstilstand",
        "duizelig", "duizeligheid", "koorts", "hoge koorts",
        "allergische reactie", "anafylaxie", "niet ademen", "stopt met ademen",
        "herseninfarct", "beroerte", "tia", "ongeluk", "val", "gevallen",
        "vergiftiging", "overdosis", "misselijk", "overgeven", "braken",
        "hoofdpijn", "ernstige hoofdpijn", "krampen", "stuipen", "epilepsie",
        "zweet", "bleek", "koud zweet",
    ],
    "medicatie": [
        "medicatie", "medicijn", "medicijnen", "bloedverdunners", "bloedverdunner",
        "insuline", "diabetes", "antibiotica", "pijnstillers", "paracetamol", "ibuprofen",
        "nitroglycerine", "nitrospray", "bloeddrukverlagers", "bloeddruk",
        "astma", "inhalator", "ventolin", "allergie", "allergisch", "penicilline",
        "medicatielijst", "medicatiedoosje", "epipen",
    ],
}


def find_keywords(text: str) -> list[dict]:
    t = text.lower()
    return [{"text": kw, "type": ktype}
            for ktype, kws in KEYWORDS.items()
            for kw in kws
            if kw in t]


# ── Sentiment model ────────────────────────────────────────────

_MODEL_PATH = os.path.join(os.path.dirname(__file__), "sentiment_model.pkl")
_model = None


def get_model():
    global _model
    if _model is None:
        with open(_MODEL_PATH, "rb") as f:
            _model = pickle.load(f)
    return _model


def predict(text: str) -> tuple[str, float]:
    model = get_model()
    proba = model.predict_proba([text])[0]
    label = model.classes_[proba.argmax()]
    return ("positief" if label == 1 else "negatief"), round(float(proba.max()), 3)


# ── Drift ──────────────────────────────────────────────────────

_window: deque[int] = deque(maxlen=100)
_DRIFT_THRESHOLD = 0.30


# ── Schemas ────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10_000)
    session_id: str | None = None

class AnalyzeResponse(BaseModel):
    sentiment: str
    confidence: float
    keywords: list[dict]
    session_id: str | None = None

class HealthResponse(BaseModel):
    status: str
    model_loaded: bool

class DriftResponse(BaseModel):
    status: str
    positive_rate: float
    drift_score: float
    samples: int


# ── App ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    get_model()
    yield

app = FastAPI(title="VitaCall API", version="1.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="healthy", model_loaded=_model is not None)


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    sentiment, confidence = predict(req.text)
    _window.append(1 if sentiment == "positief" else 0)
    return AnalyzeResponse(sentiment=sentiment, confidence=confidence,
                           keywords=find_keywords(req.text), session_id=req.session_id)


@app.get("/drift", response_model=DriftResponse)
async def drift():
    n = len(_window)
    if n < 10:
        return DriftResponse(status="onvoldoende_data", positive_rate=0.0, drift_score=0.0, samples=n)
    pos_rate = sum(_window) / n
    score = abs(pos_rate - 0.5)
    return DriftResponse(status="drift_gedetecteerd" if score > _DRIFT_THRESHOLD else "normaal",
                         positive_rate=round(pos_rate, 3), drift_score=round(score, 3), samples=n)
