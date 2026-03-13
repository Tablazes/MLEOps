"""Silver: Clean and validate Common Voice audio metadata."""
import re
from pyspark.sql import SparkSession, functions as F

def _to_snake_case(name):
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower().replace(" ", "_").replace("-", "_")

def clean_audio_metadata(spark, bronze_path, output_path):
    """Bronze -> Silver: lowercase columns, filter duration, remove nulls, deduplicate."""
    df = spark.read.parquet(bronze_path)
    for col_name in df.columns:
        df = df.withColumnRenamed(col_name, _to_snake_case(col_name))
    df = df.filter((F.col("duration") >= 1.0) & (F.col("duration") <= 30.0))
    df = df.filter(F.col("sentence").isNotNull() & (F.trim(F.col("sentence")) != ""))
    df = df.dropDuplicates(["client_id", "sentence"])
    df.write.mode("overwrite").parquet(output_path)
