"""Pytest configuratie: zorg dat sentiment_model.pkl bestaat vóór de tests."""
import pytest
from pipeline.train import _SEED_DATA, train

MODEL_PATH = "pipeline/sentiment_model.pkl"


def pytest_configure(config):
    """Train het model op seed-data als het nog niet bestaat."""
    import os
    if not os.path.exists(MODEL_PATH):
        texts  = [t for t, _ in _SEED_DATA]
        labels = [1 if l == "pos" else 0 for _, l in _SEED_DATA]
        train(texts, labels, MODEL_PATH)
