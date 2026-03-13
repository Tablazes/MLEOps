"""Bronze: Ingest Mozilla Common Voice (NL) into Parquet."""
import os
import tarfile
import requests
from pyspark.sql import SparkSession, functions as F

def ingest_common_voice(spark, tsv_path, output_path):
    """Read Common Voice validated.tsv -> Parquet."""
    df = (spark.read.option("header", "true").option("delimiter", "\t").option("quote", "").csv(tsv_path))
    df = (df
        .withColumn("up_votes", F.col("up_votes").cast("int"))
        .withColumn("down_votes", F.col("down_votes").cast("int"))
        .withColumn("duration", F.col("duration").cast("double")))
    df = df.select("client_id", "path", "sentence", "up_votes", "down_votes", "age", "gender", "duration")
    df.write.mode("overwrite").parquet(output_path)

def download_common_voice(target_dir, url=None):
    """Download + extract Common Voice. Returns path to validated.tsv."""
    tsv_path = os.path.join(target_dir, "cv-corpus", "nl", "validated.tsv")
    if os.path.exists(tsv_path):
        return tsv_path
    if url is None:
        raise FileNotFoundError(
            f"Dataset not found at {tsv_path}. Download manually from https://commonvoice.mozilla.org/nl/datasets")
    tar_path = os.path.join(target_dir, "cv-corpus-nl.tar.gz")
    if not os.path.exists(tar_path):
        resp = requests.get(url, stream=True)
        resp.raise_for_status()
        with open(tar_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(path=target_dir)
    return tsv_path
