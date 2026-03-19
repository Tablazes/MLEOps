"""MLflow experiment tracking en model registry wrapper."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

logger = logging.getLogger("vitacall")


class ExperimentTracker:
    """Wrapper rondom MLflow voor experiment tracking en model registry."""

    def __init__(self, experiment_name: str = "vitacall-mlops",
                 tracking_uri: str = "mlruns"):
        import mlflow
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(experiment_name)
        self.experiment_name = experiment_name
        self._mlflow = mlflow
        self._client = mlflow.tracking.MlflowClient(tracking_uri)

    def log_run(self, model_type: str, params: dict, metrics: dict,
                model=None, tags: dict | None = None) -> str:
        """Log een trainingsrun inclusief hyperparameters, metrics en optioneel model."""
        with self._mlflow.start_run(
            run_name=f"{model_type}_{datetime.now():%Y%m%d_%H%M}"
        ) as run:
            self._mlflow.log_params(params)
            self._mlflow.log_metrics(metrics)
            self._mlflow.set_tag("model_type", model_type)
            if tags:
                for k, v in tags.items():
                    self._mlflow.set_tag(k, v)
            if model is not None:
                self._mlflow.sklearn.log_model(model, artifact_path="model")
            logger.info("MLflow run: %s  id=%s", model_type, run.info.run_id)
            return run.info.run_id

    def compare_runs(self) -> pd.DataFrame:
        """Geef alle runs als vergelijkingstabel terug."""
        exp = self._mlflow.get_experiment_by_name(self.experiment_name)
        if exp is None:
            return pd.DataFrame()
        runs = self._client.search_runs(experiment_ids=[exp.experiment_id])
        return pd.DataFrame([
            {"run_id": r.info.run_id[:8], **r.data.params, **r.data.metrics}
            for r in runs
        ])
