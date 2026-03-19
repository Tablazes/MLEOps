"""Pipeline-configuratie en SparkSession factory."""
import logging
import os
from dataclasses import dataclass

from pyspark.sql import SparkSession

logger = logging.getLogger("vitacall")


@dataclass
class PipelineConfig:
    """Centrale configuratie voor alle pipeline-paden en parameters."""

    base_dir: str = "data"
    seed: int = 42

    @property
    def raw_dir(self) -> str:
        return os.path.join(self.base_dir, "raw")

    @property
    def bronze_dir(self) -> str:
        return os.path.join(self.base_dir, "bronze")

    @property
    def silver_dir(self) -> str:
        return os.path.join(self.base_dir, "silver")

    @property
    def gold_dir(self) -> str:
        return os.path.join(self.base_dir, "gold")

    def ensure_dirs(self) -> None:
        for d in [self.raw_dir, self.bronze_dir, self.silver_dir, self.gold_dir]:
            os.makedirs(d, exist_ok=True)


def get_spark_session(app_name: str = "VitaCall-MLOps") -> SparkSession:
    """Maak of haal een geconfigureerde SparkSession op."""
    return (
        SparkSession.builder
        .master("local[*]")
        .appName(app_name)
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.ui.enabled", "false")
        .config("spark.driver.memory", "4g")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .getOrCreate()
    )
