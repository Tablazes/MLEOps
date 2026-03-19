"""Bronze: ingest Mozilla Common Voice (NL) en IMDb reviews naar Parquet."""
import os
import tarfile
import requests
import pandas as pd
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import StructType, StructField, StringType, IntegerType


def _download_tar(url: str, tar_path: str, target_dir: str) -> None:
    if not os.path.exists(tar_path):
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(tar_path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(path=target_dir)


# ── Common Voice ──────────────────────────────────────────────

def ingest_common_voice(spark: SparkSession, tsv_path: str, output_path: str) -> None:
    (spark.read.option("header", "true").option("delimiter", "\t").option("quote", "").csv(tsv_path)
     .withColumn("up_votes",   F.col("up_votes").cast("int"))
     .withColumn("down_votes", F.col("down_votes").cast("int"))
     .withColumn("duration",   F.col("duration").cast("double"))
     .select("client_id", "path", "sentence", "up_votes", "down_votes", "age", "gender", "duration")
     .write.mode("overwrite").parquet(output_path))


def download_common_voice(target_dir: str, url: str | None = None) -> str:
    tsv_path = os.path.join(target_dir, "cv-corpus", "nl", "validated.tsv")
    if os.path.exists(tsv_path):
        return tsv_path
    if url is None:
        raise FileNotFoundError(
            f"Dataset niet gevonden op {tsv_path}. "
            "Download via https://commonvoice.mozilla.org/nl/datasets")
    _download_tar(url, os.path.join(target_dir, "cv-corpus-nl.tar.gz"), target_dir)
    return tsv_path


# ── IMDb ───────────────────────────────────────────────────────

IMDB_URL = "https://ai.stanford.edu/~amaas/data/sentiment/aclImdb_v1.tar.gz"


def ingest_imdb(_spark: SparkSession, imdb_dir: str, output_path: str) -> None:
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
                    text = f.read()
                review_id = f"{split}_{sentiment}_{fname[:-4]}"
                rows.append((review_id, text, label, f"{split}/{sentiment}/{fname}"))
    os.makedirs(output_path, exist_ok=True)
    (pd.DataFrame(rows, columns=["review_id", "text", "label", "source_file"])
     .to_parquet(os.path.join(output_path, "imdb.parquet"), index=False))


def download_imdb(target_dir: str, url: str = IMDB_URL) -> str:
    imdb_dir = os.path.join(target_dir, "aclImdb")
    if not os.path.exists(imdb_dir):
        _download_tar(url, os.path.join(target_dir, "aclImdb_v1.tar.gz"), target_dir)
    return imdb_dir


# ── Sentiment140 ───────────────────────────────────────────────

SENTIMENT140_SCHEMA = StructType([
    StructField("target", IntegerType(), False),
    StructField("ids",    StringType(),  False),
    StructField("date",   StringType(),  True),
    StructField("flag",   StringType(),  True),
    StructField("user",   StringType(),  True),
    StructField("text",   StringType(),  False),
])


def ingest_sentiment140(spark: SparkSession, csv_path: str, output_path: str) -> None:
    (spark.read.option("header", "false").option("encoding", "ISO-8859-1")
     .schema(SENTIMENT140_SCHEMA).csv(csv_path)
     .withColumn("label", (F.col("target") == 4).cast("int"))
     .select("ids", "text", "label", "user", "date")
     .write.mode("overwrite").parquet(output_path))
