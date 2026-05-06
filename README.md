# VitaCall

VitaCall is een Nederlandse alarmcentrale. Een medewerker neemt een telefoontje aan, en moet binnen seconden inschatten hoe ernstig de situatie is. Dit project geeft die medewerker een tweede paar oren: een sentiment-classifier die meeluistert, spoed-keywords highlight, en aanslaat als iets uit de hand loopt.

Twee modellen. Eentje draait in de cloud achter een FastAPI-service. De andere draait offline in een Electron desktop-app, voor als het netwerk wegvalt op het slechtste moment. Het hele MLOps-deel zit eromheen: data-pipeline met validatie, hyperparameter-sweep, MLflow-tracking, drift-detectie, GitHub Actions voor continuous training. Alles staat in een notebook, zodat je elke stap kunt volgen zonder door zes mappen te zoeken.

## Wat zit waar

- `main.ipynb`: alles. Datapipeline, training, evaluatie, FastAPI-service, monitoring.
- `serve.py`: productie-versie van de API. Dezelfde code als in het notebook, los gezet voor `uvicorn` en `Dockerfile`.
- `Dockerfile`: bouwt een container die `serve.py` draait.
- `requirements.txt`: pinned versions voor reproduceerbare installs.
- `.github/workflows/`: CI (tests + docker-build) en CT (wekelijkse retraining).
- `electron/`: desktop-app met live monitoring-paneel. Gebruikt de cloud-API als die er is, valt anders terug op het lokale edge-model.
- `data/`: wordt aangemaakt door het notebook (DBRD download + drie pipeline-lagen).
- `models/`: wordt aangemaakt door het notebook (heavy + lite + federated pickles).

## Quickstart

```bash
# Train de modellen.
pip install -r requirements.txt
jupyter notebook main.ipynb            # interactief
jupyter nbconvert --to notebook --execute main.ipynb   # of headless

# Start de API lokaal.
uvicorn serve:app --host 0.0.0.0 --port 8000

# Of in Docker.
docker build -t vitacall .
docker run -p 8000:8000 vitacall

# Start de Electron app (gebruikt models/sentiment_lite.json automatisch).
cd electron
npm install
npm run dev      # browser, op http://localhost:5173
npm start        # native desktop window
```

## Hoe het werkt

110k Nederlandse boekenrecensies van Hebban.nl (DBRD) als basis, plus een handmatige set spoed-zinnen die we 100x oversamplen. Boeken-Nederlands en alarmcentrale-Nederlands lijken niet op elkaar, dus zonder die augmentatie scoort het model goed op recensies en slecht op echte triage-zinnen.

TF-IDF features (1-2 grams, 5000 dimensies) plus logistic regression. Resultaat: ~87% F1 op de DBRD test-set, met de Nederlandse sanity-checks die uit de domein-zinnen komen ook groen. Het lite-model voor de edge gooit features omlaag naar 800 unigrams en levert een ~6x kleiner pickle in voor 5% accuracy-verlies.

De FastAPI-service serveert vier endpoints, allemaal JSON:

- `GET /health`: liveness check.
- `POST /analyze`: tekst in, sentiment + confidence + keywords uit.
- `GET /metrics`: uptime, p50/p95 latency, error rate, gemiddelde confidence.
- `GET /drift`: positive-rate over laatste 100 predicties, met threshold-alert in de logs.

De Electron app pollt `/metrics` en `/drift` elke vijf seconden zodat de medewerker meteen ziet of de cloud-API leeft. Cloud weg? De app schakelt over op de offline scoring, en dat staat in de UI als badge bij elke uitkomst.

## Stack

Python 3.11, scikit-learn, FastAPI, MLflow, PySpark (optioneel, met pandas-fallback). Frontend: Electron, Vite, React. Continuous training via GitHub Actions cron op zondagochtend.
