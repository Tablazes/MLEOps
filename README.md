# VitaCall

VitaCall is een Nederlandse alarmcentrale. Een medewerker neemt een telefoontje aan en moet binnen seconden inschatten hoe ernstig de situatie is. Dit project geeft die medewerker een tweede paar oren: een sentiment-classifier die meeluistert, spoed-keywords highlight, en aanslaat als iets uit de hand loopt.

Twee modellen. Eentje draait in de cloud achter een FastAPI-service. De andere draait offline in een Electron desktop-app, voor als het netwerk wegvalt op het slechtste moment. Het hele MLOps-deel zit eromheen: data-pipeline met validatie, hyperparameter-sweep, MLflow-tracking, drift-detectie en GitHub Actions voor continuous training.

## Quickstart

```powershell
# Simpelste pad: backend + frontend tegelijk in een venster.
pip install -r requirements.txt
pwsh -File run.ps1                # dev (uvicorn :8000 + vite :5173)
pwsh -File run.ps1 -Mode prod     # docker compose stack
```

Eerste keer? Voer `main.ipynb` uit zodat `models/sentiment_heavy.pkl` bestaat. Ctrl+C ruimt beide processen op.

Losse onderdelen als je liever stap voor stap werkt:

```powershell
jupyter nbconvert --to notebook --execute main.ipynb   # train + evalueer headless
uvicorn serve:app --host 0.0.0.0 --port 8000           # alleen API
docker build -t vitacall . ; docker run -p 8000:8000 vitacall
cd electron ; npm install ; npm start                  # native desktop window
```

## Rubric -> Bewijs

| Leerdoel                            | Niveau     | Notebook-sectie                | Evidence                                             |
| ----------------------------------- | ---------- | ------------------------------ | ---------------------------------------------------- |
| LD1 Datapipeline + validatie        | basis      | 1.1 - 1.3                      | `data/MANIFEST.json`, `data/trainklaar/`             |
| LD2 Schaalbaarheid (streaming/Spark) | gevorderd  | 1.4 - 1.7                      | `evidence/scaling_benchmark.json`                    |
| LD3 Modellering + tracking          | gevorderd  | 2.1 - 2.5                      | `models/*.pkl`, `mlruns/`, `evidence/model_card.md`  |
| LD3+ Federated + Bayesian tuning    | excellent  | 2.6, 2.8                       | `models/sentiment_federated.pkl`                     |
| LD3 Plots als bewijs                | basis      | 2.7                            | `evidence/{confusion_matrix,roc_curve,calibration}.png`, `evidence/model_comparison.csv` |
| LD4 Deployment (API + edge)         | gevorderd  | 3.1 - 3.3                      | `serve.py`, `Dockerfile`, `electron/`                |
| LD4+ Docker-compose + integratie    | excellent  | 3.5 - 3.6                      | `docker-compose.yml`, `evidence/k8s_deployment.yaml`, `evidence/integration_audit.md` |
| LD5 Monitoring + drift              | gevorderd  | 4.1 - 4.3                      | `evidence/drift_report.json`, `evidence/metrics.prom` |
| LD5+ PSI/KS + alert-engine          | excellent  | 4.4 - 4.5                      | `evidence/alerts.jsonl`                              |
| CI/CT (continuous training)         | gevorderd  | -                              | `.github/workflows/{ci,ct}.yml`                      |

## Wat zit waar

```
main.ipynb            alle code, in volgorde van de leerdoelen hierboven
serve.py              productie-API (uvicorn target, dezelfde code als 3.1)
run.ps1               start backend + frontend tegelijk
Dockerfile            container voor serve.py
data/                 ruw/, schoon/, trainklaar/ + MANIFEST.json (SHA256s)
models/               sentiment_heavy.pkl, sentiment_lite.pkl, sentiment_federated.pkl
evidence/             alle bewijs: plots, CSVs, JSONs, model card, k8s/grafana/prometheus
docker-compose.yml    api + mlflow + prometheus stack (zie sectie 3.5)
mlruns/               MLflow-tracking store (sectie 2.5)
electron/             desktop-app: live monitoring + edge-model fallback
.github/workflows/    ci.yml (tests + docker-build), ct.yml (wekelijkse retraining)
```

## Hoe het werkt

110k Nederlandse boekenrecensies van Hebban.nl (DBRD) als basis, plus een handmatige set spoed-zinnen die we 100x oversamplen. Boeken-Nederlands en alarmcentrale-Nederlands lijken niet op elkaar, dus zonder die augmentatie scoort het model goed op recensies en slecht op echte triage-zinnen.

TF-IDF features (1-2 grams, 5000 dimensies) plus logistic regression. Resultaat: ~87% F1 op de DBRD test-set, met de Nederlandse sanity-checks groen. Het lite-model voor de edge gooit features omlaag naar 800 unigrams en levert een ~6x kleiner pickle voor 5% accuracy-verlies.

De FastAPI-service serveert vier endpoints: `GET /health`, `POST /analyze`, `GET /metrics`, `GET /drift`. De Electron app pollt `/health` elke 3 seconden zodat de medewerker meteen ziet of de cloud-API leeft. Cloud weg? De app schakelt over op de offline scoring met een badge bij elke uitkomst.

WebRTC-signalering tussen operator en mobiele beller loopt via `BroadcastChannel`. Dat werkt alleen binnen één browser-context (zelfde origin, zelfde proces) — voor de demo open je beide views in één Electron-window of in twee tabs van dezelfde Chrome.

## Stack

Python 3.11, scikit-learn, FastAPI, MLflow, PySpark (optioneel, met pandas-fallback). Frontend: Electron, Vite, React. Continuous training via GitHub Actions cron op zondagochtend.
