"""Gold: feature engineering voor ASR en sentiment — gestratificeerde splits."""
from functools import reduce
from pyspark.sql import SparkSession, functions as F


def create_asr_features(spark: SparkSession, silver_path: str, output_path: str, seed: int = 42) -> None:
    df = spark.read.parquet(silver_path)
    tr, va, te = df.randomSplit([0.8, 0.1, 0.1], seed=seed)
    (tr.withColumn("split", F.lit("train"))
       .unionByName(va.withColumn("split", F.lit("val")))
       .unionByName(te.withColumn("split", F.lit("test")))
       .withColumn("duration_bucket",
           F.when(F.col("duration") < 5.0,  "short")
            .when(F.col("duration") <= 15.0, "medium")
            .otherwise("long"))
       .write.mode("overwrite").parquet(output_path))


def create_sentiment_features(spark: SparkSession, silver_path: str, output_path: str, seed: int = 42) -> None:
    df = spark.read.parquet(silver_path)
    parts = []
    for label_val in [0, 1]:
        tr, va, te = df.filter(F.col("label") == label_val).randomSplit([0.8, 0.1, 0.1], seed=seed)
        parts += [tr.withColumn("split", F.lit("train")),
                  va.withColumn("split", F.lit("val")),
                  te.withColumn("split", F.lit("test"))]
    (reduce(lambda a, b: a.unionByName(b), parts)
     .withColumn("token_count", F.size(F.split(F.col("text_clean"), r"\s+")))
     .write.mode("overwrite").parquet(output_path))
