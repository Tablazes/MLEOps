"""Render OperatorDashboard + CallerScreen offscreen naar PNG voor visuele review.

    python evidence/shot_ui.py
Genereert evidence/<date>_operator.png en _caller.png. Simuleert een korte
call zodat transcript/contactkaart gevuld zijn.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests
from PySide6.QtWidgets import QApplication

from app.backend import start_api_server
from app.models import EdgeModel
from app.ui import CallerScreen, OperatorDashboard
from app.widgets import STYLE

API = "http://127.0.0.1:8000"
EV = ROOT / "evidence"


def pump(app: QApplication, seconds: float) -> None:
    t0 = time.time()
    while time.time() - t0 < seconds:
        app.processEvents()
        time.sleep(0.02)


def main() -> int:
    start_api_server(ROOT / "models" / "sentiment_heavy.pkl", API)
    for _ in range(30):
        try:
            if requests.get(f"{API}/health", timeout=0.5).ok:
                break
        except requests.RequestException:
            pass
        time.sleep(0.2)

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    edge = EdgeModel.load(ROOT / "models" / "sentiment_lite.json")

    op = OperatorDashboard(edge, API)
    caller = CallerScreen(API)
    op.resize(1180, 760)
    caller.resize(420, 820)
    op.show()
    caller.show()
    pump(app, 0.8)

    # Korte call zodat de contactkaart + transcript gevuld zijn op de shot.
    requests.post(f"{API}/call/start", json={"caller": "Luis Coderque"}, timeout=2)
    pump(app, 0.8)
    op._on_accept()
    pump(app, 0.8)
    for line in ["goedemiddag met de alarmcentrale",
                 "ik ben gevallen en heb pijn op de borst",
                 "ik gebruik een bloedverdunner",
                 "het gaat nu wat beter dank je wel"]:
        requests.post(f"{API}/call/transcript", json={"text": line}, timeout=2)
        pump(app, 0.5)
    pump(app, 0.6)

    prefix = date.today().isoformat()
    op_png = EV / f"{prefix}_operator_tahoe.png"
    caller_png = EV / f"{prefix}_caller_tahoe.png"
    op.grab().save(str(op_png))
    caller.grab().save(str(caller_png))
    print(f"saved {op_png}")
    print(f"saved {caller_png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
