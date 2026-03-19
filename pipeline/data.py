"""VitaCall data pipeline: bronze → silver → gold (IMDb, Common Voice, Sentiment140)."""
from __future__ import annotations

import logging
import os
import re
import tarfile

import pandas as pd
import requests
from functools import reduce
from pyspark.sql import SparkSession, functions as F

logger = logging.getLogger("vitacall")

# ── Spark ──────────────────────────────────────────────────────

def get_spark(app: str = "VitaCall") -> SparkSession:
    return (SparkSession.builder.master("local[*]").appName(app)
            .config("spark.sql.shuffle.partitions", "4")
            .config("spark.ui.enabled", "false")
            .config("spark.driver.memory", "4g")
            .getOrCreate())

# ── Bronze ─────────────────────────────────────────────────────

IMDB_URL = "https://ai.stanford.edu/~amaas/data/sentiment/aclImdb_v1.tar.gz"


# ── Common Voice (batch + streaming bron) ──────────────────────

def ingest_common_voice(spark: SparkSession, tsv_path: str, out: str) -> None:
    """Bronze: Mozilla Common Voice NL → Parquet (batch ingestie)."""
    (spark.read.option("header", "true").option("delimiter", "\t").option("quote", "").csv(tsv_path)
     .withColumn("up_votes",   F.col("up_votes").cast("int"))
     .withColumn("down_votes", F.col("down_votes").cast("int"))
     .withColumn("duration",   F.col("duration").cast("double"))
     .select("client_id", "path", "sentence", "up_votes", "down_votes", "age", "gender", "duration")
     .write.mode("overwrite").parquet(out))


def clean_audio(spark: SparkSession, bronze: str, out: str) -> None:
    """Silver: duur filteren, nulls en dubbelen verwijderen."""
    df = spark.read.parquet(bronze)
    (df.filter((F.col("duration") >= 1.0) & (F.col("duration") <= 30.0)
               & F.col("sentence").isNotNull() & (F.trim(F.col("sentence")) != ""))
       .dropDuplicates(["client_id", "sentence"])
       .write.mode("overwrite").parquet(out))


# ── Sentiment140 (batch, 1.6M tweets) ─────────────────────────

def ingest_sentiment140(spark: SparkSession, csv_path: str, out: str) -> None:
    """Bronze: Sentiment140 CSV → Parquet (groot volume, streaming-achtige bron)."""
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


# ── Gold ───────────────────────────────────────────────────────

def create_sentiment_features(spark: SparkSession, silver: str, out: str, seed: int = 42) -> None:
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
    from pipeline.train import train

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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run()
