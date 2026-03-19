"""VitaCall — datapipeline (bronze→silver→gold) + training + federatief leren."""
from __future__ import annotations

import argparse
import logging
import os
import pickle
import tarfile

import numpy as np
import pandas as pd
import requests
from functools import reduce
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import Pipeline

try:
    import mlflow
    import mlflow.sklearn
    _MLFLOW = True
except ImportError:
    _MLFLOW = False

logger = logging.getLogger("vitacall")

# ── Seed-data (voor tests + fallback training) ──────────────────

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

# ── Model bouwen ────────────────────────────────────────────────

def _build() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=5000)),
        ("clf",   LogisticRegression(max_iter=500, random_state=42)),
    ])

# ── Lokaal trainen ──────────────────────────────────────────────

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
    if _MLFLOW:
        with mlflow.start_run():
            mlflow.log_params({"n_samples": len(texts), "ngram_range": "1,2", "max_features": 5000})
            if metrics:
                mlflow.log_metrics(metrics)
            mlflow.sklearn.log_model(model, "sentiment_model")
    return metrics

# ── Federatief trainen (FedAvg) ─────────────────────────────────

def federated_train(client_data: list[tuple[list[str], list[int]]],
                    output_path: str, rounds: int = 3) -> None:
    """FedAvg: train lokale modellen per client, middel de coëfficiënten."""
    global_model = None
    for ronde in range(1, rounds + 1):
        coefs, intercepts = [], []
        for texts, labels in client_data:
            m = _build()
            m.fit(texts, labels)
            coefs.append(m.named_steps["clf"].coef_)
            intercepts.append(m.named_steps["clf"].intercept_)
        global_model = _build()
        all_texts = [t for texts, _ in client_data for t in texts]
        all_labels = [l for _, labels in client_data for l in labels]
        global_model.fit(all_texts, all_labels)
        global_model.named_steps["clf"].coef_      = np.mean(coefs, axis=0)
        global_model.named_steps["clf"].intercept_ = np.mean(intercepts, axis=0)
        print(f"  Ronde {ronde}/{rounds} — {len(client_data)} clients gemiddeld")
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(output_path, "wb") as f:
        pickle.dump(global_model, f)
    print(f"Federatief model opgeslagen: {output_path}")

# ── Spark ──────────────────────────────────────────────────────

def get_spark(app: str = "VitaCall"):
    from pyspark.sql import SparkSession
    return (SparkSession.builder.master("local[*]").appName(app)
            .config("spark.sql.shuffle.partitions", "4")
            .config("spark.ui.enabled", "false")
            .config("spark.driver.memory", "4g")
            .getOrCreate())

# ── Bronze ─────────────────────────────────────────────────────

IMDB_URL = "https://ai.stanford.edu/~amaas/data/sentiment/aclImdb_v1.tar.gz"


def ingest_common_voice(spark, tsv_path: str, out: str) -> None:
    """Bronze: Mozilla Common Voice NL → Parquet."""
    from pyspark.sql import functions as F
    (spark.read.option("header", "true").option("delimiter", "\t").option("quote", "").csv(tsv_path)
     .withColumn("up_votes",   F.col("up_votes").cast("int"))
     .withColumn("down_votes", F.col("down_votes").cast("int"))
     .withColumn("duration",   F.col("duration").cast("double"))
     .select("client_id", "path", "sentence", "up_votes", "down_votes", "age", "gender", "duration")
     .write.mode("overwrite").parquet(out))


def ingest_sentiment140(spark, csv_path: str, out: str) -> None:
    """Bronze: Sentiment140 CSV → Parquet (1.6M tweets)."""
    from pyspark.sql import functions as F
    from pyspark.sql.types import StructType, StructField, StringType, IntegerType
    schema = StructType([
        StructField("target", IntegerType(), False),
        StructField("ids",    StringType(),  False),
        StructField("date",   StringType(),  True),
        StructField("flag",   StringType(),  True),
        StructField("user",   StringType(),  True),
        StructField("text",   StringType(),  False),
    ])
    (spark.read.option("header", "false").option("encoding", "ISO-8859-1")
     .schema(schema).csv(csv_path)
     .withColumn("label", (F.col("target") == 4).cast("int"))
     .select("ids", "text", "label", "user", "date")
     .write.mode("overwrite").parquet(out))


def download_imdb(base_dir: str = "data") -> str:
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
        for sentiment in ["pos", "neg"]:
            label = 1 if sentiment == "pos" else 0
            sdir = os.path.join(imdb_dir, split, sentiment)
            if not os.path.isdir(sdir):
                continue
            for fname in os.listdir(sdir):
                if not fname.endswith(".txt"):
                    continue
                with open(os.path.join(sdir, fname), encoding="utf-8") as f:
                    rows.append((f"{split}_{sentiment}_{fname[:-4]}", f.read(),
                                 label, f"{split}/{sentiment}/{fname}"))
    os.makedirs(out, exist_ok=True)
    pd.DataFrame(rows, columns=["review_id", "text", "label", "source_file"]).to_parquet(
        os.path.join(out, "imdb.parquet"), index=False)

# ── Silver ─────────────────────────────────────────────────────

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


def clean_audio(spark, bronze: str, out: str) -> None:
    """Silver: duur filteren, nulls en dubbelen verwijderen."""
    from pyspark.sql import functions as F
    df = spark.read.parquet(bronze)
    (df.filter((F.col("duration") >= 1.0) & (F.col("duration") <= 30.0)
               & F.col("sentence").isNotNull() & (F.trim(F.col("sentence")) != ""))
       .dropDuplicates(["client_id", "sentence"])
       .write.mode("overwrite").parquet(out))

# ── Gold ───────────────────────────────────────────────────────

def create_sentiment_features(spark, silver: str, out: str, seed: int = 42) -> None:
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

# ── Orchestrator ───────────────────────────────────────────────

def run(base_dir: str = "data", model_out: str = "pipeline/sentiment_model.pkl") -> None:
    """Bronze → silver → gold → train in één aanroep."""
    bronze = os.path.join(base_dir, "bronze", "imdb", "imdb.parquet")
    silver = os.path.join(base_dir, "silver", "imdb")
    gold   = os.path.join(base_dir, "gold",   "imdb")

    for d in [os.path.join(base_dir, p) for p in ("bronze", "silver", "gold")]:
        os.makedirs(d, exist_ok=True)

    if not os.path.exists(bronze):
        logger.info("Bronze: downloaden...")
        ingest_imdb(download_imdb(base_dir), os.path.dirname(bronze))

    logger.info("Silver: cleaning...")
    clean_reviews(bronze, silver)

    logger.info("Gold: splits aanmaken...")
    spark = get_spark()
    spark.sparkContext.setLogLevel("WARN")
    create_sentiment_features(spark, silver, gold)
    spark.stop()

    df = pd.read_parquet(gold)
    tr = df[df["split"] == "train"]
    logger.info("Train: %d voorbeelden...", len(tr))
    train(tr["text_clean"].tolist(), tr["label"].tolist(), model_out)


def _load_parquet(data_dir: str):
    df = pd.read_parquet(data_dir)
    tr = df[df["split"] == "train"]
    return tr["text_clean"].tolist(), tr["label"].tolist()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=None)
    parser.add_argument("--out",  default="pipeline/sentiment_model.pkl")
    args = parser.parse_args()
    if args.data:
        texts, labels = _load_parquet(args.data)
        train(texts, labels, args.out)
    else:
        run(model_out=args.out)
