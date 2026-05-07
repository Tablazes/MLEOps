# VitaCall

Nederlandse alarmcentrale-assistent. Luistert mee tijdens telefoongesprekken: sentiment-classifier, spoed-keywords, drift-detectie. Pure Python stack — geen npm, geen JavaScript.

## Starten

**1. Model trainen (eerste keer)**

```powershell
pip install -r requirements.txt
jupyter nbconvert --to notebook --execute main.ipynb
```

`models/sentiment_heavy.pkl` en `models/sentiment_lite.json` worden aangemaakt.

**2. Backend**

```powershell
uvicorn serve:app --host 127.0.0.1 --port 8000
```

Of via Docker:

```powershell
docker compose up
```

**3. Desktop UI**

```powershell
pip install -r requirements.txt
python app/ui.py              # operator (alarmcentrale)
python app/ui.py --mobile     # beller
```

Start beide vensters naast elkaar voor een volledige demo. De UI valt automatisch terug op het lokale edge-model als de backend offline is.

## Wat zit waar

```
main.ipynb            alle code: pipeline, training, evaluatie, monitoring
serve.py              FastAPI-service (uvicorn target)
app/ui.py             PySide6 desktop UI (operator + mobile view)
requirements.txt      backend/notebook dependencies
requirements-ui.txt   UI dependencies (PySide6, sounddevice, vosk)
run-ui.ps1            PowerShell launcher voor de UI
Dockerfile            container voor serve.py
docker-compose.yml    api + mlflow + prometheus stack
data/                 ruw/, schoon/, trainklaar/ + MANIFEST.json
models/               sentiment_heavy.pkl, sentiment_lite.pkl, sentiment_federated.pkl, sentiment_lite.json
mlruns/               MLflow tracking store
.github/workflows/    ci.yml + ct.yml (continuous training)
```

## Rubric → Bewijs

| Leerdoel | Niveau | Notebook-sectie |
|---|---|---|
| LD1 Datapipeline + validatie | basis | 1.1 – 1.3 |
| LD2 Schaalbaarheid (streaming/Spark) | gevorderd | 1.4 – 1.7 |
| LD3 Modellering + tracking | gevorderd | 2.1 – 2.5 |
| LD3+ Federated + Bayesian tuning | excellent | 2.6, 2.8 |
| LD4 Deployment (API + edge) | gevorderd | 3.1 – 3.3 |
| LD4+ Docker-compose + integratie | excellent | 3.5 – 3.6 |
| LD5 Monitoring + drift | gevorderd | 4.1 – 4.3 |
| LD5+ PSI/KS + alert-engine | excellent | 4.4 – 4.5 |

## Hoe het werkt

110k Nederlandse boekenrecensies (DBRD) als basis, plus handmatige spoed-zinnen die 100x oversampeld worden. TF-IDF features (1-2 grams, 5000 dims) + logistic regression. ~87% F1 op DBRD test-set.

FastAPI serveert `GET /health`, `POST /analyze`, `GET /metrics`, `GET /drift`. De desktop UI pollt `/health` elke 3 seconden en schakelt automatisch over op edge-scoring als de cloud weg is.

Signalering tussen operator en beller loopt via een lokaal JSON-bestand (`signaling.json`). Beide vensters draaien onafhankelijk — geen browser, geen Electron.

## Stack

Python 3.11, scikit-learn, FastAPI, MLflow, PySide6, PySpark (optioneel). Continuous training via GitHub Actions cron.
