"""Train sentiment model — lokaal (TF-IDF + LR) en federatief (FedAvg)."""
import os
import pickle
import argparse
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import Pipeline

_SEED_DATA = [
    ("goed","pos"),("prima","pos"),("beter","pos"),("rustig","pos"),
    ("geen klachten","pos"),("stabiel","pos"),("oké","pos"),("normaal","pos"),
    ("kalm","pos"),("dank","pos"),("fijn","pos"),("begrepen","pos"),
    ("helder","pos"),("alles goed","pos"),("geen pijn","pos"),
    ("ik voel me goed","pos"),("het gaat prima","pos"),("geen problemen","pos"),
    ("pijn","neg"),("benauwd","neg"),("bloeding","neg"),("bewusteloos","neg"),
    ("misselijk","neg"),("hoofdpijn","neg"),("koorts","neg"),("hartaanval","neg"),
    ("ernstig","neg"),("help","neg"),("erg pijn","neg"),("gevallen","neg"),
    ("niet ademen","neg"),("stuipen","neg"),("overdosis","neg"),
    ("ik heb veel pijn","neg"),("het gaat slecht","neg"),
    ("ik kan niet ademen","neg"),("erg benauwd","neg"),
    ("pijn op de borst","neg"),("bloed verlies","neg"),
]


def _build() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=5000)),
        ("clf",   LogisticRegression(max_iter=500, random_state=42)),
    ])


def train(texts: list[str], labels: list[int], output_path: str,
          val_texts: list[str] | None = None, val_labels: list[int] | None = None) -> dict:
    model = _build()
    model.fit(texts, labels)
    metrics: dict = {}
    if val_texts:
        preds = model.predict(val_texts)
        metrics = {"accuracy": round(accuracy_score(val_labels, preds), 4),
                   "f1":       round(f1_score(val_labels, preds, average="weighted"), 4)}
        print(f"  Accuracy={metrics['accuracy']:.2%}  F1={metrics['f1']:.2%}")
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(output_path, "wb") as f:
        pickle.dump(model, f)
    print(f"Model opgeslagen: {output_path}  ({len(texts)} voorbeelden)")
    return metrics


def federated_train(client_data: list[tuple[list[str], list[int]]],
                    output_path: str, rounds: int = 3) -> None:
    """FedAvg: train lokale modellen per client, middel de coëfficiënten.

    Args:
        client_data: Lijst van (texts, labels) per gesimuleerde client.
        output_path: Pad voor het geaggregeerde model.
        rounds:      Aantal federatieve rondes.
    """
    global_model = None
    for ronde in range(1, rounds + 1):
        coefs, intercepts = [], []
        for texts, labels in client_data:
            m = _build()
            m.fit(texts, labels)
            coefs.append(m.named_steps["clf"].coef_)
            intercepts.append(m.named_steps["clf"].intercept_)
        # FedAvg: gemiddeld over clients
        global_model = _build()
        all_texts = [t for texts, _ in client_data for t in texts]
        all_labels = [l for _, labels in client_data for l in labels]
        global_model.fit(all_texts, all_labels)            # fit voor vocabulaire
        global_model.named_steps["clf"].coef_      = np.mean(coefs, axis=0)
        global_model.named_steps["clf"].intercept_ = np.mean(intercepts, axis=0)
        print(f"  Ronde {ronde}/{rounds} — {len(client_data)} clients gemiddeld")
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(output_path, "wb") as f:
        pickle.dump(global_model, f)
    print(f"Federatief model opgeslagen: {output_path}")


def _load_parquet(data_dir: str):
    df = pd.read_parquet(data_dir)
    train = df[df["split"] == "train"]
    return train["text_clean"].tolist(), train["label"].tolist()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=None)
    parser.add_argument("--out",  default="pipeline/sentiment_model.pkl")
    args = parser.parse_args()
    texts, labels = (_load_parquet(args.data) if args.data else
                     ([t for t, _ in _SEED_DATA], [1 if l == "pos" else 0 for _, l in _SEED_DATA]))
    train(texts, labels, args.out)
