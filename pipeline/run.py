"""Pipeline orchestrator: bronze → silver → gold → train."""
from __future__ import annotations

import logging
import os

from pipeline.bronze import download_imdb, ingest_imdb
from pipeline.config import PipelineConfig, get_spark_session
from pipeline.gold import create_sentiment_features
from pipeline.silver import clean_reviews
from pipeline.train import train

logger = logging.getLogger("vitacall")


def run_pipeline(base_dir: str = "data", model_out: str = "pipeline/sentiment_model.pkl") -> None:
    """Voer de volledige IMDb-pipeline uit: bronze → silver → gold → train."""
    cfg = PipelineConfig(base_dir=base_dir)
    cfg.ensure_dirs()

    bronze_path = os.path.join(cfg.bronze_dir, "imdb", "imdb.parquet")
    silver_path = os.path.join(cfg.silver_dir, "imdb")
    gold_path   = os.path.join(cfg.gold_dir,   "imdb")

    spark = get_spark_session()
    spark.sparkContext.setLogLevel("WARN")

    # Bronze
    if not os.path.exists(bronze_path):
        logger.info("Bronze: IMDb downloaden...")
        imdb_dir = download_imdb(base_dir)
        ingest_imdb(spark, imdb_dir, os.path.dirname(bronze_path))

    # Silver
    logger.info("Silver: reviews schoonmaken...")
    clean_reviews(spark, bronze_path, silver_path)

    # Gold
    logger.info("Gold: features aanmaken...")
    create_sentiment_features(spark, silver_path, gold_path)

    spark.stop()

    # Train
    import pandas as pd
    df = pd.read_parquet(gold_path)
    train_df = df[df["split"] == "train"]
    logger.info("Train: %d voorbeelden...", len(train_df))
    train(train_df["text_clean"].tolist(), train_df["label"].tolist(), model_out)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_pipeline()
