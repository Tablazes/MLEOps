"""Edge-model scoring + cloud API health check."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

import requests

API_URL = "http://127.0.0.1:8000"

URGENT = ["pijn", "borst", "benauwd", "bewusteloos", "bloed", "hartaanval",
          "koorts", "flauwgevallen", "gevallen", "niet ademen", "overdosis"]
MEDS = ["paracetamol", "ibuprofen", "insuline", "antibiotica", "medicatie",
        "bloedverdunner", "inhalator", "epipen"]


def find_keywords(text: str) -> list[dict]:
    t = text.lower()
    out = [{"text": k, "type": "urgentie"} for k in URGENT if k in t]
    out += [{"text": k, "type": "medicatie"} for k in MEDS if k in t]
    return out


@dataclass
class EdgeModel:
    vocab: dict[str, int]
    idf: list[float]
    coef: list[float]
    bias: float

    @classmethod
    def load(cls, path: Path) -> "EdgeModel | None":
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return cls(d["vocab"], d["idf"], d["coef"], float(d["bias"]))

    def score(self, text: str) -> dict | None:
        tokens = re.findall(r"[a-zàáâäçèéêëìíîïñòóôöùúûü']+", text.lower())
        if not tokens:
            return None
        tf: dict[str, int] = {}
        for tok in tokens:
            tf[tok] = tf.get(tok, 0) + 1
        s = self.bias
        n = len(tokens)
        for tok, count in tf.items():
            i = self.vocab.get(tok)
            if i is not None:
                s += (count / n) * self.idf[i] * self.coef[i]
        p = 1 / (1 + math.exp(-s))
        return {"sentiment": "positief" if p > 0.5 else "negatief", "confidence": round(max(p, 1 - p), 3)}


def score_text(text: str, edge: EdgeModel | None) -> dict | None:
    """Cloud-eerst scoring met edge-fallback."""
    try:
        r = requests.post(f"{API_URL}/analyze", json={"text": text}, timeout=1.5)
        if r.ok:
            d = r.json()
            d["source"] = "cloud"
            return d
    except requests.RequestException:
        pass
    if edge is None:
        return None
    res = edge.score(text)
    if res is None:
        return None
    res["keywords"] = find_keywords(text)
    res["source"] = "edge"
    return res


def api_health() -> bool:
    try:
        r = requests.get(f"{API_URL}/health", timeout=0.7)
        return r.ok
    except requests.RequestException:
        return False
