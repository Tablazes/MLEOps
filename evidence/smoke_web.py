"""Headless test: backend mount serves web/ + full call flow via HTTP."""
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import requests
from app.backend import start_api_server

API = "http://127.0.0.1:8000"
ok = []
def chk(n, c, d=""):
    ok.append(c); print(f"{'PASS' if c else 'FAIL'}  {n}" + (f"  ({d})" if d else ""))

start_api_server(ROOT/"models"/"sentiment_heavy.pkl", API)
for _ in range(40):
    try:
        if requests.get(f"{API}/health", timeout=0.5).ok: break
    except requests.RequestException: pass
    time.sleep(0.25)

chk("health", requests.get(f"{API}/health").json().get("status")=="healthy")
# served static
idx = requests.get(f"{API}/", timeout=3)
chk("GET / serves index.html", idx.ok and "VitaCall" in idx.text, f"status={idx.status_code}")
chk("/ links operator+caller", "operator.html" in idx.text and "caller.html" in idx.text)
op = requests.get(f"{API}/operator.html", timeout=3)
chk("operator.html served", op.ok and "operator.js" in op.text)
ca = requests.get(f"{API}/caller.html", timeout=3)
chk("caller.html served", ca.ok and "caller.js" in ca.text)
cssr = requests.get(f"{API}/css/app.css", timeout=3)
chk("app.css served", cssr.ok and "no gradient" in cssr.text.lower())
chk("css has NO gradient decl", "linear-gradient" not in cssr.text and "radial-gradient" not in cssr.text)
apijs = requests.get(f"{API}/js/api.js", timeout=3)
chk("api.js served", apijs.ok and "export" in apijs.text)
# API routes still win over the static mount
chk("API route /call/state still works", requests.get(f"{API}/call/state", timeout=2).json().get("phase")=="idle")
# full call flow
requests.post(f"{API}/call/start", json={"caller":"Test"}, timeout=2)
chk("start->ringing", requests.get(f"{API}/call/state").json()["phase"]=="ringing")
requests.post(f"{API}/call/accept", timeout=2)
chk("accept->active", requests.get(f"{API}/call/state").json()["phase"]=="active")
requests.post(f"{API}/call/transcript", json={"text":"ik ben gevallen en heb pijn op de borst"}, timeout=2)
st = requests.get(f"{API}/call/state").json()
chk("transcript line stored", len(st["events"])>=1, f"events={len(st['events'])}")
an = requests.post(f"{API}/analyze", json={"text":"ik ben gevallen en heb pijn op de borst"}, timeout=3).json()
chk("analyze returns sentiment+keywords", "sentiment" in an and any(k["type"]=="urgentie" for k in an.get("keywords",[])), str(an.get("keywords")))
requests.post(f"{API}/call/end", timeout=2)
chk("end->idle", requests.get(f"{API}/call/state").json()["phase"]=="idle")
time.sleep(0.2)
chk("history has the call", len(requests.get(f"{API}/call/history").json()["calls"])>=1)

p=sum(ok); t=len(ok)
print(f"\n{'='*46}\n{p}/{t} checks passed")
sys.exit(0 if p==t else 1)
