"""Tests voor pipeline zonder Spark-afhankelijkheid."""
import os
import tempfile

import pandas as pd
import pytest

from pipeline.api import find_keywords, predict
from pipeline.data import clean_reviews, ingest_imdb, _SEED_DATA, train, federated_train


# ── find_keywords ──────────────────────────────────────────────

def test_find_keywords_urgentie():
    results = find_keywords("ik heb pijn op de borst")
    types = [r["type"] for r in results]
    assert "urgentie" in types

def test_find_keywords_medicatie():
    results = find_keywords("ik gebruik paracetamol en insuline")
    types = [r["type"] for r in results]
    assert "medicatie" in types

def test_find_keywords_leeg():
    assert find_keywords("alles goed") == []

def test_find_keywords_geen_duplicaten():
    results = find_keywords("pijn op de borst en borstpijn")
    teksten = [r["text"] for r in results]
    assert len(teksten) == len(set(teksten))


# ── predict ────────────────────────────────────────────────────

def test_predict_retourneert_tuple():
    sentiment, confidence = predict("ik heb pijn")
    assert sentiment in ("positief", "negatief")
    assert 0.0 <= confidence <= 1.0

def test_predict_negatief():
    sentiment, _ = predict("ernstige pijn op de borst, bewusteloos")
    assert sentiment == "negatief"

def test_predict_positief():
    sentiment, _ = predict("het gaat goed, stabiel, geen klachten")
    assert sentiment == "positief"


# ── train ──────────────────────────────────────────────────────

def test_train_maakt_model():
    texts  = [t for t, _ in _SEED_DATA]
    labels = [1 if l == "pos" else 0 for _, l in _SEED_DATA]
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
        path = f.name
    try:
        train(texts, labels, path)
        assert os.path.getsize(path) > 0
    finally:
        os.unlink(path)

def test_train_geeft_metrics():
    texts  = [t for t, _ in _SEED_DATA]
    labels = [1 if l == "pos" else 0 for _, l in _SEED_DATA]
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
        path = f.name
    try:
        metrics = train(texts, labels, path, val_texts=texts, val_labels=labels)
        assert "accuracy" in metrics and "f1" in metrics
        assert 0.0 <= metrics["accuracy"] <= 1.0
    finally:
        os.unlink(path)

def test_federated_train():
    texts  = [t for t, _ in _SEED_DATA]
    labels = [1 if l == "pos" else 0 for _, l in _SEED_DATA]
    # Elke client krijgt beide klassen (gesimuleerd met dezelfde data)
    clients = [(texts, labels), (texts, labels)]
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
        path = f.name
    try:
        federated_train(clients, path, rounds=2)
        assert os.path.getsize(path) > 0
    finally:
        os.unlink(path)


# ── clean_reviews ──────────────────────────────────────────────

def test_clean_reviews_verwijdert_html():
    with tempfile.TemporaryDirectory() as tmp:
        bronze = os.path.join(tmp, "bronze.parquet")
        silver = os.path.join(tmp, "silver")
        pd.DataFrame([
            ("id1", "<p>Great film!</p>", 1, "train/pos/1.txt"),
            ("id2", "<b>Terrible</b>",    0, "train/neg/2.txt"),
            ("id3", "",                   1, "train/pos/3.txt"),  # leeg → gefilterd
        ], columns=["review_id", "text", "label", "source_file"]).to_parquet(bronze)

        clean_reviews(bronze, silver)
        df = pd.read_parquet(silver)

        assert len(df) == 2
        assert not df["text_clean"].str.contains("<").any()
        assert "split" in df.columns
