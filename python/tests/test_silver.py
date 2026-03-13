import os
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType
from pipelines.silver.clean_audio_metadata import clean_audio_metadata
from pipelines.silver.clean_reviews import clean_reviews

CV_SCHEMA = StructType([
    StructField("client_id", StringType()), StructField("path", StringType()),
    StructField("sentence", StringType()), StructField("up_votes", IntegerType()),
    StructField("down_votes", IntegerType()), StructField("age", StringType()),
    StructField("gender", StringType()), StructField("duration", DoubleType()),
])

IMDB_SCHEMA = StructType([
    StructField("review_id", StringType()), StructField("text", StringType()),
    StructField("label", IntegerType()), StructField("source_file", StringType()),
])


class TestCleanAudio:
    def test_filters_duration(self, spark, tmp_dir):
        data = [("a","a.mp3","Kort",1,0,None,None,0.5), ("b","b.mp3","Goed",1,0,None,None,5.0), ("c","c.mp3","Lang",1,0,None,None,35.0)]
        spark.createDataFrame(data, schema=CV_SCHEMA).write.parquet(f"{tmp_dir}/b")
        clean_audio_metadata(spark, f"{tmp_dir}/b", f"{tmp_dir}/s")
        assert spark.read.parquet(f"{tmp_dir}/s").count() == 1

    def test_removes_null_sentences(self, spark, tmp_dir):
        data = [("a","a.mp3",None,1,0,None,None,5.0), ("b","b.mp3","",1,0,None,None,5.0), ("c","c.mp3","OK",1,0,None,None,5.0)]
        spark.createDataFrame(data, schema=CV_SCHEMA).write.parquet(f"{tmp_dir}/b")
        clean_audio_metadata(spark, f"{tmp_dir}/b", f"{tmp_dir}/s")
        assert spark.read.parquet(f"{tmp_dir}/s").count() == 1

    def test_dedup(self, spark, tmp_dir):
        data = [("a","a1.mp3","Hallo",1,0,None,None,5.0), ("a","a2.mp3","Hallo",2,0,None,None,6.0), ("b","b.mp3","Hallo",1,0,None,None,5.0)]
        spark.createDataFrame(data, schema=CV_SCHEMA).write.parquet(f"{tmp_dir}/b")
        clean_audio_metadata(spark, f"{tmp_dir}/b", f"{tmp_dir}/s")
        assert spark.read.parquet(f"{tmp_dir}/s").count() == 2

    def test_lowercase_columns(self, spark, tmp_dir):
        schema = StructType([
            StructField("Client_ID", StringType()), StructField("Path", StringType()),
            StructField("Sentence", StringType()), StructField("Up_Votes", IntegerType()),
            StructField("Down_Votes", IntegerType()), StructField("Age", StringType()),
            StructField("Gender", StringType()), StructField("Duration", DoubleType()),
        ])
        spark.createDataFrame([("a","a.mp3","Test",1,0,None,None,5.0)], schema=schema).write.parquet(f"{tmp_dir}/b")
        clean_audio_metadata(spark, f"{tmp_dir}/b", f"{tmp_dir}/s")
        for c in spark.read.parquet(f"{tmp_dir}/s").columns:
            assert c == c.lower()


class TestCleanReviews:
    def test_strips_html(self, spark, tmp_dir):
        data = [("r1", "<p>Great <b>movie</b>!</p>", 1, "f.txt")]
        spark.createDataFrame(data, schema=IMDB_SCHEMA).write.parquet(f"{tmp_dir}/b")
        clean_reviews(spark, f"{tmp_dir}/b", f"{tmp_dir}/s")
        row = spark.read.parquet(f"{tmp_dir}/s").collect()[0]
        assert "<" not in row["text_clean"]
        assert "Great" in row["text_clean"]

    def test_removes_empty(self, spark, tmp_dir):
        data = [("r1", "<br/>", 1, "f.txt"), ("r2", "Real text", 0, "f.txt")]
        spark.createDataFrame(data, schema=IMDB_SCHEMA).write.parquet(f"{tmp_dir}/b")
        clean_reviews(spark, f"{tmp_dir}/b", f"{tmp_dir}/s")
        assert spark.read.parquet(f"{tmp_dir}/s").count() == 1

    def test_dedup(self, spark, tmp_dir):
        data = [("r1","Same",1,"f.txt"), ("r2","Same",0,"f.txt"), ("r3","Diff",1,"f.txt")]
        spark.createDataFrame(data, schema=IMDB_SCHEMA).write.parquet(f"{tmp_dir}/b")
        clean_reviews(spark, f"{tmp_dir}/b", f"{tmp_dir}/s")
        assert spark.read.parquet(f"{tmp_dir}/s").count() == 2
