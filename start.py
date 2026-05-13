"""VitaCall launcher: opent operator-dashboard + mobile call-screen in 1 commando.

    python start.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UI = ROOT / "app" / "ui.py"


def main() -> None:
    if not UI.exists():
        print(f"FAIL: {UI} ontbreekt")
        sys.exit(1)
    # Verwijder oude signaling-state zodat de twee vensters fris starten.
    (ROOT / "signaling.json").unlink(missing_ok=True)

    creation = 0
    if sys.platform == "win32":
        creation = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]

    print("==> start operator-dashboard...")
    op = subprocess.Popen([sys.executable, str(UI)], cwd=str(ROOT), creationflags=creation)
    time.sleep(2)  # wacht tot backend up
    print("==> start mobile call-screen...")
    mob = subprocess.Popen([sys.executable, str(UI), "--mobile"], cwd=str(ROOT), creationflags=creation)

    print(f"\nVitaCall draait. PIDs: operator={op.pid} mobile={mob.pid}")
    print("Sluit beide vensters om te stoppen, of Ctrl+C hier.")

    try:
        op.wait()
        mob.wait()
    except KeyboardInterrupt:
        for p in (op, mob):
            try:
                p.terminate()
            except OSError:
                pass


if __name__ == "__main__":
    main()
