"""Data drift monitoring via Population Stability Index (PSI)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger("vitacall")


class DriftMonitor:
    """PSI-gebaseerde drift detectie voor numerieke en tekstfeatures.

    PSI > 0.1 = waarschuwing, PSI > 0.2 = kritiek (Yurdakul, 2020).
    """

    PSI_THRESHOLD_WARNING = 0.1
    PSI_THRESHOLD_CRITICAL = 0.2

    def __init__(self, reference_data: pd.DataFrame, n_bins: int = 10):
        self.reference_data = reference_data
        self.n_bins = n_bins
        self.drift_history: list[dict[str, Any]] = []

    def calculate_psi(self, reference: np.ndarray, current: np.ndarray) -> float:
        """Bereken Population Stability Index tussen twee distributies."""
        eps = 1e-6
        bins = np.linspace(
            min(reference.min(), current.min()),
            max(reference.max(), current.max()),
            self.n_bins + 1,
        )
        ref_counts, _ = np.histogram(reference, bins=bins)
        cur_counts, _ = np.histogram(current, bins=bins)
        ref_pct = (ref_counts + eps) / (ref_counts.sum() + eps * len(ref_counts))
        cur_pct = (cur_counts + eps) / (cur_counts.sum() + eps * len(cur_counts))
        return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))

    def _status(self, psi: float) -> str:
        if psi > self.PSI_THRESHOLD_CRITICAL:
            return "CRITICAL"
        if psi > self.PSI_THRESHOLD_WARNING:
            return "WARNING"
        return "OK"

    def check_numeric_drift(
        self, current_data: pd.DataFrame, columns: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Controleer numerieke kolommen op drift."""
        results = {}
        for col in columns:
            if col not in self.reference_data.columns or col not in current_data.columns:
                continue
            ref = self.reference_data[col].dropna().values
            cur = current_data[col].dropna().values
            if len(ref) == 0 or len(cur) == 0:
                continue
            psi = self.calculate_psi(ref, cur)
            results[col] = {
                "psi": round(psi, 4), "status": self._status(psi),
                "ref_mean": round(float(ref.mean()), 4),
                "cur_mean": round(float(cur.mean()), 4),
                "ref_std":  round(float(ref.std()), 4),
                "cur_std":  round(float(cur.std()), 4),
            }
        self.drift_history.append({"timestamp": datetime.now().isoformat(), "results": results})
        return results

    def check_text_drift(
        self, reference_texts: list[str], current_texts: list[str],
    ) -> dict[str, Any]:
        """Controleer tekstdata op drift via token-lengte distributie."""
        ref_lengths = np.array([len(t.split()) for t in reference_texts])
        cur_lengths = np.array([len(t.split()) for t in current_texts])
        psi = self.calculate_psi(ref_lengths, cur_lengths)
        return {
            "token_length_psi": round(psi, 4),
            "status": self._status(psi),
            "ref_mean_tokens": round(float(ref_lengths.mean()), 2),
            "cur_mean_tokens": round(float(cur_lengths.mean()), 2),
        }
