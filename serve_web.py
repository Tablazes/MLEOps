"""VitaCall web launcher.

Start de FastAPI-backend (die nu ook de web-frontend serveert), wacht tot
/health gezond is, opent de operator-UI in de standaardbrowser en blijft
draaien tot je Ctrl+C of Enter geeft.

Gebruik:
    python serve_web.py

De backend draait in een daemon-thread; dit script blokkeert daarom zelf
zodat het proces in leven blijft. Pure stdlib + requests.
"""
from __future__ import annotations

import sys
import time
import webbrowser
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
HEAVY_MODEL_PATH = ROOT / "models" / "sentiment_heavy.pkl"
API_URL = "http://127.0.0.1:8000"


def _wait_for_health(url: str, timeout_s: float = 30.0) -> bool:
    """Poll GET /health tot status 'healthy' of timeout. True bij succes."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            resp = requests.get(f"{url}/health", timeout=2)
            if resp.ok and resp.json().get("status") == "healthy":
                return True
        except requests.RequestException:
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    """Start backend, wacht op health, open browser, blijf draaien."""
    sys.path.insert(0, str(ROOT))
    from app.backend import start_api_server

    if not HEAVY_MODEL_PATH.exists():
        print(f"[serve_web] model niet gevonden: {HEAVY_MODEL_PATH}", file=sys.stderr)
        return 1

    print(f"[serve_web] backend starten ({API_URL}) ...")
    start_api_server(HEAVY_MODEL_PATH, API_URL)

    if not _wait_for_health(API_URL):
        print("[serve_web] backend werd niet gezond binnen de timeout", file=sys.stderr)
        return 1

    print(f"[serve_web] gezond — browser openen op {API_URL}/")
    webbrowser.open(f"{API_URL}/")

    print("[serve_web] draait. Druk Enter of Ctrl+C om te stoppen.")
    try:
        input()
    except (KeyboardInterrupt, EOFError):
        pass
    print("[serve_web] gestopt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
