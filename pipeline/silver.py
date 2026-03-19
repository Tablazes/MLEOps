"""Silver: schoonmaken en valideren van audio-metadata en reviews."""
import os
import re
import pandas as pd
from pyspark.sql import SparkSession, functions as F


# ── Common Voice ──────────────────────────────────────────────

def _snake(name: str) -> str:
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower().replace(" ", "_").replace("-", "_")


def clean_audio_metadata(spark: SparkSession, bronze_path: str, output_path: str) -> None:
    """Bronze → Silver: kolommen lowercasen, duur filteren, nulls en dubbelen verwijderen."""
    df = spark.read.parquet(bronze_path)
    for col in df.columns:
        df = df.withColumnRenamed(col, _snake(col))
    df = (df
          .filter((F.col("duration") >= 1.0) & (F.col("duration") <= 30.0)
                  & F.col("sentence").isNotNull() & (F.trim(F.col("sentence")) != ""))
          .dropDuplicates(["client_id", "sentence"]))
    df.write.mode("overwrite").parquet(output_path)


# ── IMDb ───────────────────────────────────────────────────────

def _strip_html(col):
    """Verwijder HTML-tags en normaliseer witruimte met pure Spark SQL."""
    return F.trim(F.regexp_replace(F.regexp_replace(col, r"<[^>]+>", " "), r"\s+", " "))


def clean_reviews(_spark: SparkSession, bronze_path: str, output_path: str) -> None:
    """Bronze → Silver: HTML strippen, labels valideren, lege en dubbele rijen verwijderen."""
    df = pd.read_parquet(bronze_path)
    df["text_clean"] = (df["text"]
                        .str.replace(r"<[^>]+>", " ", regex=True)
                        .str.replace(r"\s+", " ", regex=True)
                        .str.strip())
    df["split"] = df["source_file"].str.split("/").str[0]
    df = (df[df["label"].isin([0, 1]) & df["text_clean"].notna() & (df["text_clean"] != "")]
          .drop_duplicates(subset=["text_clean"])
          .reset_index(drop=True))
    os.makedirs(output_path, exist_ok=True)
    df.to_parquet(os.path.join(output_path, "imdb.parquet"), index=False)
