"""Gold: Sentiment feature engineering -- stratified splits and token counts."""
from pyspark.sql import SparkSession, functions as F

def create_sentiment_features(spark, silver_path, output_path, seed=42):
    """Silver -> Gold: stratified 80/10/10 splits + token counts."""
    df = spark.read.parquet(silver_path)
    pos = df.filter(F.col("label") == 1)
    neg = df.filter(F.col("label") == 0)
    parts = []
    for subset in [pos, neg]:
        tr, va, te = subset.randomSplit([0.8, 0.1, 0.1], seed=seed)
        parts.extend([
            tr.withColumn("split", F.lit("train")),
            va.withColumn("split", F.lit("val")),
            te.withColumn("split", F.lit("test")),
        ])
    df = parts[0]
    for p in parts[1:]:
        df = df.unionByName(p)
    df = df.withColumn("token_count", F.size(F.split(F.col("text_clean"), r"\s+")))
    df.write.mode("overwrite").parquet(output_path)
