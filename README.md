# VitaCall

Nederlandse alarmcentrale-assistent. Sentiment-classifier, spoed-keywords, drift-detectie. Pure Python.

## Starten

**1. Trainen (eerste keer):**

```powershell
pip install -r requirements.txt
jupyter nbconvert --to notebook --execute main.ipynb
```

Genereert `models/sentiment_heavy.pkl`, `models/sentiment_lite.json`, en alle `evidence/*` artefacten.

**2. Desktop UI** (backend start mee als daemon-thread):

```powershell
python app/ui.py              # operator-window + backend
python app/ui.py --mobile     # beller-window
```

Backend extern: `uvicorn serve:app` + `python app/ui.py --no-server`.

**3. Docker:**

```powershell
docker compose up             # api + mlflow + prometheus
```

## Structuur

```
main.ipynb              alle code: pipeline, training, deployment, monitoring
serve.py                FastAPI-service voor productie
app/ui.py               PySide6 operator/beller-window + entrypoint
app/backend.py          embedded FastAPI backend
app/models.py           EdgeModel, score_text, api_health, find_keywords
app/signals.py          FileBus + AudioBridge (sounddevice + vosk)
app/widgets.py          STYLE, StackedBar, HoldButton, make_metric_box
Dockerfile              productie-container
docker-compose.yml      api + mlflow + prometheus stack
monitoring/prometheus.yml
.github/workflows/cicd.yml   CI + CD + CT in 1 workflow
evidence/               plots + JSON-rapporten (gegenereerd door notebook)
models/sentiment_heavy.pkl   het cloud-model (lite-versie auto-gegenereerd)
```

## Rubric → bewijs

| Leerdoel | Sectie notebook | Evidence-file |
|---|---|---|
| LD1 Datapipeline + validatie | 1.1 – 1.3 | `evidence/validation_report.json`, `data/MANIFEST.json` |
| LD2 Schaalbaarheid (streaming/Spark/cloud) | 1.4 – 1.7 | `evidence/throughput.png`, `evidence/scaling_benchmark.json` |
| LD3 Modellering (CV + tuning + tracking) | 2.1 – 2.5 | `evidence/cv_scores.json`, `evidence/confusion_matrix.png`, `evidence/roc_curve.png`, `evidence/calibration.png`, `evidence/model_comparison.csv`, `reports/model_card.md` |
| LD3+ Federated + Bayesian (Optuna) | 2.6, 2.8 | MLflow runs in `mlruns/` |
| LD4 Deployment (API + edge + Docker) | 3.1 – 3.6 | `Dockerfile`, `docker-compose.yml`, `k8s/deployment.yaml`, CI logs |
| LD5 Monitoring + drift (output + PSI/KS) | 4.1 – 4.5 | `evidence/drift_report.json`, `evidence/metrics.prom`, `evidence/alerts.jsonl`, `evidence/monitoring_timeseries.png`, `monitoring/grafana/vitacall_dashboard.json` |

## Cijfers (gemeten)

| Metric | Doel | Werkelijk |
|---|---|---|
| Test-accuracy heavy | ≥ 0.85 | 0.871 |
| CV-F1 mean (5-fold) | ≥ 0.80 | 0.848 ± 0.056 |
| Pickle heavy | ≤ 1 MB | 0.22 MB |
| Pickle lite | ≤ 100 KB | 36 KB |
| Inference p95 | ≤ 50 ms | ~5–15 ms |

## Hoe het werkt

DBRD-dataset, labeled deel (~22k recensies, 110k incl. unsup). TF-IDF (1–2 grams, 5000 dims) + logistic regression. Plus 100x oversampled spoed-zinnen voor zorg-domein.

FastAPI serveert `/health`, `/analyze`, `/drift`, `/metrics`. Desktop UI pollt `/health` elke 3 sec en valt terug op edge-model (`sentiment_lite.json`) als de cloud weg is.

Signalering operator ↔ beller via lokaal JSON-bestand (`signaling.json`).

## CI/CD/CT

`.github/workflows/cicd.yml` heeft 3 jobs:
1. **test** (push/PR): smoke-test alle endpoints.
2. **docker-build** (push/PR): bouwt image, container-health-check.
3. **retrain** (schedule zondag 03:00 UTC / handmatig): voert notebook end-to-end uit, uploadt modellen als artifact.

## Stack

Python 3.11 · scikit-learn · FastAPI · MLflow · PySide6 · PySpark (optioneel) · Optuna · Prometheus · GitHub Actions
