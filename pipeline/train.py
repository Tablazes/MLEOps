"""Train sentiment model (TF-IDF + Logistic Regression)."""
import os
import pickle
import argparse
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
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


def train(texts: list[str], labels: list[int], output_path: str) -> None:
    model = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=5000)),
        ("clf",   LogisticRegression(max_iter=500, random_state=42)),
    ])
    model.fit(texts, labels)
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(output_path, "wb") as f:
        pickle.dump(model, f)
    print(f"Model opgeslagen: {output_path}  ({len(texts)} voorbeelden)")


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
