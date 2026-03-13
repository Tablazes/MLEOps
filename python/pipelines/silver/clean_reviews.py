"""Silver: Clean and validate IMDb reviews."""
import re
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import StringType

def _strip_html(text):
    if text is None:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", clean).strip()

strip_html_udf = F.udf(_strip_html, StringType())

def clean_reviews(spark, bronze_path, output_path):
    """Bronze -> Silver: strip HTML, validate labels, remove empties, deduplicate."""
    df = spark.read.parquet(bronze_path)
    df = df.withColumn("text_clean", strip_html_udf(F.col("text")))
    df = df.filter(F.col("label").isin(0, 1))
    df = df.filter(F.col("text_clean").isNotNull() & (F.trim(F.col("text_clean")) != ""))
    df = df.dropDuplicates(["text_clean"])
    df.write.mode("overwrite").parquet(output_path)
