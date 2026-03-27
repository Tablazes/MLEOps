import logging
import os
import pickle

import numpy as np
import pandas as pd
import requests
from functools import reduce
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import Pipeline

try:
    import mlflow, mlflow.sklearn
    _MLFLOW = True
except ImportError:
    _MLFLOW = False

logger = logging.getLogger("vitacall")

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


def train(texts: list, labels: list, output_path: str,
          val_texts: list | None = None, val_labels: list | None = None) -> dict:
    model = _build()
    model.fit(texts, labels)
    metrics = {}
    if val_texts:
        preds = model.predict(val_texts)
        metrics = {"accuracy": round(accuracy_score(val_labels, preds), 4),
                   "f1":       round(f1_score(val_labels, preds, average="weighted"), 4)}
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as f:
        pickle.dump(model, f)
    if _MLFLOW:
        with mlflow.start_run():
            mlflow.log_params({"n_samples": len(texts), "ngram_range": "1,2", "max_features": 5000})
            if metrics:
                mlflow.log_metrics(metrics)
            mlflow.sklearn.log_model(model, "sentiment_model")
    return metrics


def federated_train(client_data: list, output_path: str, rounds: int = 3) -> None:
    global_model = None
    for ronde in range(1, rounds + 1):
        coefs      = [_build().fit(t, l).named_steps["clf"].coef_      for t, l in client_data]
        intercepts = [_build().fit(t, l).named_steps["clf"].intercept_ for t, l in client_data]
        all_texts  = [t for texts, _ in client_data for t in texts]
        all_labels = [l for _, labels in client_data for l in labels]
        global_model = _build()
        global_model.fit(all_texts, all_labels)
        global_model.named_steps["clf"].coef_      = np.mean(coefs, axis=0)
        global_model.named_steps["clf"].intercept_ = np.mean(intercepts, axis=0)
        logger.info("Ronde %d/%d — %d clients", ronde, rounds, len(client_data))
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as f:
        pickle.dump(global_model, f)


def get_spark(app: str = "VitaCall"):
    from pyspark.sql import SparkSession
    return (SparkSession.builder.master("local[*]").appName(app)
            .config("spark.sql.shuffle.partitions", "4")
            .config("spark.ui.enabled", "false")
            .config("spark.driver.memory", "4g")
            .getOrCreate())


IMDB_URL = "https://ai.stanford.edu/~amaas/data/sentiment/aclImdb_v1.tar.gz"


def download_imdb(base_dir: str = "data") -> str:
    import tarfile
    imdb_dir = os.path.join(base_dir, "aclImdb")
    if not os.path.exists(imdb_dir):
        tar_path = os.path.join(base_dir, "aclImdb_v1.tar.gz")
        if not os.path.exists(tar_path):
            with requests.get(IMDB_URL, stream=True) as r:
                r.raise_for_status()
                with open(tar_path, "wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(path=base_dir)
    return imdb_dir


def ingest_imdb(imdb_dir: str, out: str) -> None:
    rows = []
    for split in ["train", "test"]:
        for sentiment, label in [("pos", 1), ("neg", 0)]:
            sdir = os.path.join(imdb_dir, split, sentiment)
            if not os.path.isdir(sdir):
                continue
            for fname in os.listdir(sdir):
                if fname.endswith(".txt"):
                    with open(os.path.join(sdir, fname), encoding="utf-8") as f:
                        rows.append((f"{split}_{sentiment}_{fname[:-4]}", f.read(),
                                     label, f"{split}/{sentiment}/{fname}"))
    os.makedirs(out, exist_ok=True)
    pd.DataFrame(rows, columns=["review_id", "text", "label", "source_file"]).to_parquet(
        os.path.join(out, "imdb.parquet"), index=False)


def clean_reviews(bronze: str, out: str) -> None:
    df = pd.read_parquet(bronze)
    df["text_clean"] = (df["text"]
                        .str.replace(r"<[^>]+>", " ", regex=True)
                        .str.replace(r"\s+", " ", regex=True)
                        .str.strip())
    df["split"] = df["source_file"].str.split("/").str[0]
    df = (df[df["label"].isin([0, 1]) & df["text_clean"].notna() & (df["text_clean"] != "")]
          .drop_duplicates(subset=["text_clean"]).reset_index(drop=True))
    os.makedirs(out, exist_ok=True)
    df.to_parquet(os.path.join(out, "imdb.parquet"), index=False)


def create_features(spark, silver: str, out: str, seed: int = 42) -> None:
    from pyspark.sql import functions as F
    df = spark.read.parquet(silver)
    parts = []
    for label_val in [0, 1]:
        tr, va, te = df.filter(F.col("label") == label_val).randomSplit([0.8, 0.1, 0.1], seed=seed)
        parts += [tr.withColumn("split", F.lit("train")),
                  va.withColumn("split", F.lit("val")),
                  te.withColumn("split", F.lit("test"))]
    (reduce(lambda a, b: a.unionByName(b), parts)
     .withColumn("token_count", F.size(F.split(F.col("text_clean"), r"\s+")))
     .write.mode("overwrite").parquet(out))


def run(base_dir: str = "data", model_out: str = "pipeline/sentiment_model.pkl") -> None:
    bronze = os.path.join(base_dir, "bronze", "imdb", "imdb.parquet")
    silver = os.path.join(base_dir, "silver", "imdb")
    gold   = os.path.join(base_dir, "gold",   "imdb")

    for d in [os.path.join(base_dir, p) for p in ("bronze", "silver", "gold")]:
        os.makedirs(d, exist_ok=True)

    if not os.path.exists(bronze):
        logger.info("Ingestie: IMDb downloaden...")
        ingest_imdb(download_imdb(base_dir), os.path.dirname(bronze))

    logger.info("Cleaning...")
    clean_reviews(bronze, silver)

    logger.info("Stratified splits...")
    spark = get_spark()
    spark.sparkContext.setLogLevel("WARN")
    create_features(spark, silver, gold)
    spark.stop()

    df = pd.read_parquet(gold)
    tr = df[df["split"] == "train"]
    logger.info("Training: %d voorbeelden...", len(tr))
    train(tr["text_clean"].tolist(), tr["label"].tolist(), model_out)


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--data", default=None)
    p.add_argument("--out",  default="pipeline/sentiment_model.pkl")
    args = p.parse_args()
    if args.data:
        df = pd.read_parquet(args.data)
        tr = df[df["split"] == "train"]
        train(tr["text_clean"].tolist(), tr["label"].tolist(), args.out)
    else:
        run(model_out=args.out)
