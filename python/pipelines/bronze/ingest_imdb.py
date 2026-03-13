"""Bronze: Ingest IMDb Reviews into Parquet."""
import os
import tarfile
import requests
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType

IMDB_URL = "https://ai.stanford.edu/~amaas/data/sentiment/aclImdb_v1.tar.gz"
IMDB_SCHEMA = StructType([
    StructField("review_id", StringType(), False),
    StructField("text", StringType(), False),
    StructField("label", IntegerType(), False),
    StructField("source_file", StringType(), False),
])

def ingest_imdb(spark, imdb_dir, output_path):
    """Parse IMDb text files -> Parquet. Expects imdb_dir/{train,test}/{pos,neg}/*.txt"""
    records = []
    for split in ["train", "test"]:
        split_dir = os.path.join(imdb_dir, split)
        if not os.path.isdir(split_dir):
            continue
        for sentiment in ["pos", "neg"]:
            sdir = os.path.join(split_dir, sentiment)
            if not os.path.isdir(sdir):
                continue
            label = 1 if sentiment == "pos" else 0
            for fname in os.listdir(sdir):
                if not fname.endswith(".txt"):
                    continue
                with open(os.path.join(sdir, fname), "r", encoding="utf-8") as f:
                    text = f.read()
                rid = f"{split}_{sentiment}_{fname.replace('.txt', '')}"
                records.append((rid, text, label, f"{split}/{sentiment}/{fname}"))
    df = spark.createDataFrame(records, schema=IMDB_SCHEMA)
    df.write.mode("overwrite").parquet(output_path)

def download_imdb(target_dir, url=IMDB_URL):
    """Download + extract IMDb. Returns path to aclImdb directory."""
    imdb_dir = os.path.join(target_dir, "aclImdb")
    if os.path.exists(imdb_dir):
        return imdb_dir
    tar_path = os.path.join(target_dir, "aclImdb_v1.tar.gz")
    if not os.path.exists(tar_path):
        resp = requests.get(url, stream=True)
        resp.raise_for_status()
        with open(tar_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(path=target_dir)
    return imdb_dir
