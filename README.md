# VitaCall

Nederlandse alarmcentrale-assistent. Beller belt naar operator-dashboard. Sentiment-classifier + spoed-keywords + drift-detectie draaien live op de transcript.

## Starten

```powershell
pip install -r requirements.txt
jupyter nbconvert --to notebook --execute main.ipynb   # eenmalig: train modellen
python start.py
```

`start.py` opent operator + caller in twee vensters. Eén klik op de groene knop in het beller-scherm start de oproep.

## Netwerk (ander apparaat als beller)

Backend bindt op `0.0.0.0:8000`, dus een ander apparaat in hetzelfde LAN kan bellen:

```powershell
# Op host-pc:
python app/ui.py                                       # operator
# Op ander apparaat (zelfde wifi):
python app/ui.py --mobile --api http://<host-ip>:8000  # beller
```

## Structuur

```
main.ipynb              pipeline + training + monitoring (alle code)
serve.py                FastAPI productie-service
app/ui.py               operator-dashboard + beller-scherm
app/backend.py          embedded API (health, analyze, drift, metrics, call/*)
app/models.py           edge scoring + cloud fallback
app/signals.py          mic-loopback
app/icons.py            vector-iconen (geen emoji)
app/widgets.py          stijl + custom widgets
start.py                launcher: opent beide vensters
Dockerfile + docker-compose.yml
.github/workflows/cicd.yml
evidence/               plots + rapporten (gegenereerd door notebook)
models/sentiment_heavy.pkl
```

## Cijfers (gemeten)

| Metric | Doel | Werkelijk |
|---|---|---|
| Test-accuracy | ≥ 0.85 | 0.871 |
| CV-F1 mean (5-fold) | ≥ 0.80 | 0.848 ± 0.056 |
| Inference p95 | ≤ 50 ms | ~5–15 ms |

## CI/CD/CT

`.github/workflows/cicd.yml` (3 jobs): test, docker-build, retrain (cron zondag 03:00 UTC).

## Stack

Python 3.11, scikit-learn, FastAPI, MLflow, PySide6, PySpark (optioneel), Optuna, Prometheus.
