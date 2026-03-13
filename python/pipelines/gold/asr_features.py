"""Gold: ASR feature engineering -- splits and duration buckets."""
from pyspark.sql import SparkSession, functions as F

def create_asr_features(spark, silver_path, output_path, seed=42):
    """Silver -> Gold: 80/10/10 splits + duration buckets."""
    df = spark.read.parquet(silver_path)
    tr, va, te = df.randomSplit([0.8, 0.1, 0.1], seed=seed)
    tr = tr.withColumn("split", F.lit("train"))
    va = va.withColumn("split", F.lit("val"))
    te = te.withColumn("split", F.lit("test"))
    df = tr.unionByName(va).unionByName(te)
    df = df.withColumn("duration_bucket",
        F.when(F.col("duration") < 5.0, "short")
        .when(F.col("duration") <= 15.0, "medium")
        .otherwise("long"))
    df.write.mode("overwrite").parquet(output_path)
