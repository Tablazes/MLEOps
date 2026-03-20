import json
import os
import pickle
from collections import deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
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
            for ktype, kws in KEYWORDS.items() for kw in kws if kw in t]


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


_window: deque[int] = deque(maxlen=100)
_DRIFT_THRESHOLD = 0.30


def _drift_snapshot() -> dict:
    n = len(_window)
    if n < 10:
        return {"status": "onvoldoende_data", "positive_rate": 0.0, "drift_score": 0.0, "samples": n}
    pos_rate = sum(_window) / n
    score = abs(pos_rate - 0.5)
    return {"status": "drift_gedetecteerd" if score > _DRIFT_THRESHOLD else "normaal",
            "positive_rate": round(pos_rate, 3), "drift_score": round(score, 3), "samples": n}


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


_ws_clients: set[WebSocket] = set()


async def _broadcast(event: dict):
    dead = set()
    msg = json.dumps(event)
    for ws in _ws_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    _ws_clients -= dead


_VOSK_MODEL_PATH = os.path.join(os.path.dirname(__file__), "vosk-model-small-nl")
_vosk_model = None


def get_vosk_model():
    global _vosk_model
    if _vosk_model is None and os.path.exists(_VOSK_MODEL_PATH):
        from vosk import Model, SetLogLevel
        SetLogLevel(-1)
        _vosk_model = Model(_VOSK_MODEL_PATH)
    return _vosk_model


def _make_recognizer():
    vosk_model = get_vosk_model()
    if vosk_model is None:
        return None
    from vosk import KaldiRecognizer
    rec = KaldiRecognizer(vosk_model, 16000)
    rec.SetWords(True)
    return rec


async def _run_asr_loop(ws: WebSocket, rec, on_final, on_partial=None):
    try:
        while True:
            data = await ws.receive_bytes()
            if rec.AcceptWaveform(data):
                text = json.loads(rec.Result()).get("text", "").strip()
                if text:
                    await on_final(text)
            else:
                text = json.loads(rec.PartialResult()).get("partial", "").strip()
                if text and on_partial:
                    await on_partial(text)
    except WebSocketDisconnect:
        text = json.loads(rec.FinalResult()).get("text", "").strip()
        if text:
            try:
                await on_final(text)
            except Exception:
                pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_model()
    get_vosk_model()
    yield

app = FastAPI(title="VitaCall API", version="1.3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="healthy", model_loaded=_model is not None)


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    sentiment, confidence = predict(req.text)
    _window.append(1 if sentiment == "positief" else 0)
    resp = AnalyzeResponse(sentiment=sentiment, confidence=confidence,
                           keywords=find_keywords(req.text), session_id=req.session_id)
    await _broadcast({"type": "analysis", "sentiment": sentiment, "confidence": confidence,
                      "keywords": resp.keywords, "drift": _drift_snapshot()})
    return resp


@app.get("/drift", response_model=DriftResponse)
async def drift():
    snap = _drift_snapshot()
    return DriftResponse(**snap)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_clients.add(ws)
    await ws.send_text(json.dumps({
        "type": "status",
        "health": {"status": "healthy", "model_loaded": _model is not None},
        "drift": _drift_snapshot(),
        "asr": get_vosk_model() is not None,
    }))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        _ws_clients.discard(ws)


@app.websocket("/asr")
async def asr_endpoint(ws: WebSocket):
    await ws.accept()
    rec = _make_recognizer()
    if rec is None:
        await ws.send_text(json.dumps({"error": "Vosk model niet gevonden"}))
        await ws.close()
        return

    async def on_final(text):
        await ws.send_text(json.dumps({"type": "final", "text": text}))

    async def on_partial(text):
        await ws.send_text(json.dumps({"type": "partial", "text": text}))

    await _run_asr_loop(ws, rec, on_final, on_partial)


@app.websocket("/mobile-asr")
async def mobile_asr_endpoint(ws: WebSocket):
    await ws.accept()
    rec = _make_recognizer()
    if rec is None:
        await ws.send_text(json.dumps({"type": "error", "message": "Vosk model niet gevonden"}))
        await ws.close()
        return

    await ws.send_text(json.dumps({"type": "connected"}))
    await _broadcast({"type": "mobile_connected"})

    async def on_final(text):
        await _broadcast({"type": "mobile_transcript", "text": text, "source": "mobile"})
        sentiment, confidence = predict(text)
        _window.append(1 if sentiment == "positief" else 0)
        await _broadcast({"type": "analysis", "sentiment": sentiment, "confidence": confidence,
                          "keywords": find_keywords(text), "drift": _drift_snapshot(), "source": "mobile"})
        await ws.send_text(json.dumps({"type": "speech_detected"}))

    async def on_partial(text):
        await _broadcast({"type": "mobile_partial", "text": text, "source": "mobile"})

    await _run_asr_loop(ws, rec, on_final, on_partial)
    await _broadcast({"type": "mobile_disconnected"})
