import os
import csv
from pipelines.bronze.ingest_common_voice import ingest_common_voice
from pipelines.bronze.ingest_imdb import ingest_imdb


class TestIngestCommonVoice:
    def test_schema_and_count(self, spark, tmp_dir):
        tsv_dir = os.path.join(tmp_dir, "cv-corpus", "nl")
        os.makedirs(tsv_dir, exist_ok=True)
        rows = [
            {"client_id": "abc", "path": "a.mp3", "sentence": "Hallo", "up_votes": "3", "down_votes": "0", "age": "twenties", "gender": "male", "duration": "2.5"},
            {"client_id": "def", "path": "b.mp3", "sentence": "Dag", "up_votes": "5", "down_votes": "1", "age": "", "gender": "", "duration": "3.1"},
        ]
        tsv_path = os.path.join(tsv_dir, "validated.tsv")
        with open(tsv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys(), delimiter="\t")
            w.writeheader()
            w.writerows(rows)
        out = os.path.join(tmp_dir, "out")
        ingest_common_voice(spark, tsv_path, out)
        df = spark.read.parquet(out)
        assert df.count() == 2
        assert set(df.columns) == {"client_id", "path", "sentence", "up_votes", "down_votes", "age", "gender", "duration"}

    def test_numeric_types(self, spark, tmp_dir):
        tsv_dir = os.path.join(tmp_dir, "cv-corpus", "nl")
        os.makedirs(tsv_dir, exist_ok=True)
        tsv_path = os.path.join(tsv_dir, "validated.tsv")
        with open(tsv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["client_id","path","sentence","up_votes","down_votes","age","gender","duration"], delimiter="\t")
            w.writeheader()
            w.writerow({"client_id":"x","path":"a.mp3","sentence":"Test","up_votes":"2","down_votes":"1","age":"","gender":"","duration":"4.2"})
        out = os.path.join(tmp_dir, "out")
        ingest_common_voice(spark, tsv_path, out)
        df = spark.read.parquet(out)
        types = {f.name: f.dataType.simpleString() for f in df.schema.fields}
        assert types["up_votes"] == "int"
        assert types["down_votes"] == "int"
        assert types["duration"] == "double"


class TestIngestImdb:
    def test_schema_and_count(self, spark, tmp_dir):
        for label_dir in ["pos", "neg"]:
            d = os.path.join(tmp_dir, "aclImdb", "train", label_dir)
            os.makedirs(d, exist_ok=True)
            for i in range(3):
                with open(os.path.join(d, f"{i}_8.txt"), "w") as f:
                    f.write(f"Review {label_dir} {i}")
        out = os.path.join(tmp_dir, "out")
        ingest_imdb(spark, os.path.join(tmp_dir, "aclImdb"), out)
        df = spark.read.parquet(out)
        assert df.count() == 6
        assert set(df.columns) == {"review_id", "text", "label", "source_file"}

    def test_labels(self, spark, tmp_dir):
        for label_dir in ["pos", "neg"]:
            d = os.path.join(tmp_dir, "aclImdb", "train", label_dir)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "0_8.txt"), "w") as f:
                f.write("text")
        out = os.path.join(tmp_dir, "out")
        ingest_imdb(spark, os.path.join(tmp_dir, "aclImdb"), out)
        df = spark.read.parquet(out)
        labels = set(r["label"] for r in df.collect())
        assert 0 in labels and 1 in labels
