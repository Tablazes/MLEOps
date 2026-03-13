import os
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType
from pipelines.gold.asr_features import create_asr_features
from pipelines.gold.sentiment_features import create_sentiment_features

CV_SILVER = StructType([
    StructField("client_id", StringType()), StructField("path", StringType()),
    StructField("sentence", StringType()), StructField("up_votes", IntegerType()),
    StructField("down_votes", IntegerType()), StructField("age", StringType()),
    StructField("gender", StringType()), StructField("duration", DoubleType()),
])

IMDB_SILVER = StructType([
    StructField("review_id", StringType()), StructField("text", StringType()),
    StructField("label", IntegerType()), StructField("source_file", StringType()),
    StructField("text_clean", StringType()),
])


class TestAsrFeatures:
    def test_adds_split(self, spark, tmp_dir):
        data = [(f"c{i}", f"{i}.mp3", f"Zin {i}", 1, 0, None, None, 5.0) for i in range(100)]
        spark.createDataFrame(data, schema=CV_SILVER).write.parquet(f"{tmp_dir}/s")
        create_asr_features(spark, f"{tmp_dir}/s", f"{tmp_dir}/g")
        df = spark.read.parquet(f"{tmp_dir}/g")
        assert "split" in df.columns
        assert set(r["split"] for r in df.select("split").distinct().collect()) == {"train", "val", "test"}

    def test_split_ratios(self, spark, tmp_dir):
        data = [(f"c{i}", f"{i}.mp3", f"Zin {i}", 1, 0, None, None, 5.0) for i in range(1000)]
        spark.createDataFrame(data, schema=CV_SILVER).write.parquet(f"{tmp_dir}/s")
        create_asr_features(spark, f"{tmp_dir}/s", f"{tmp_dir}/g")
        df = spark.read.parquet(f"{tmp_dir}/g")
        total = df.count()
        assert 0.70 < df.filter(df.split == "train").count() / total < 0.90

    def test_duration_buckets(self, spark, tmp_dir):
        data = [("a","a.mp3","K",1,0,None,None,2.0), ("b","b.mp3","M",1,0,None,None,10.0), ("c","c.mp3","L",1,0,None,None,20.0)]
        spark.createDataFrame(data, schema=CV_SILVER).write.parquet(f"{tmp_dir}/s")
        create_asr_features(spark, f"{tmp_dir}/s", f"{tmp_dir}/g")
        buckets = {r["client_id"]: r["duration_bucket"] for r in spark.read.parquet(f"{tmp_dir}/g").collect()}
        assert buckets["a"] == "short"
        assert buckets["b"] == "medium"
        assert buckets["c"] == "long"


class TestSentimentFeatures:
    def test_stratified_splits(self, spark, tmp_dir):
        data = [(f"r{i}", f"text {i}", i % 2, f"f{i}.txt", f"clean {i}") for i in range(100)]
        spark.createDataFrame(data, schema=IMDB_SILVER).write.parquet(f"{tmp_dir}/s")
        create_sentiment_features(spark, f"{tmp_dir}/s", f"{tmp_dir}/g")
        df = spark.read.parquet(f"{tmp_dir}/g")
        for split_name in ["train", "val", "test"]:
            labels = set(r["label"] for r in df.filter(df.split == split_name).select("label").distinct().collect())
            assert 0 in labels and 1 in labels

    def test_token_count(self, spark, tmp_dir):
        data = [("r1","raw",1,"f.txt","three word sentence"), ("r2","raw",0,"f.txt","one")]
        spark.createDataFrame(data, schema=IMDB_SILVER).write.parquet(f"{tmp_dir}/s")
        create_sentiment_features(spark, f"{tmp_dir}/s", f"{tmp_dir}/g")
        counts = {r["review_id"]: r["token_count"] for r in spark.read.parquet(f"{tmp_dir}/g").collect()}
        assert counts["r1"] == 3
        assert counts["r2"] == 1
