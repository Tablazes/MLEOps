# VitaCall — MLOps eindopdracht

Nederlandse alarmcentrale: spraakgestuurde triage met een volledige MLOps-keten.
Twee onafhankelijke modellen:

- **Edge** = Vosk-NL ASR (spraak → tekst), draait lokaal/offline op het toestel van de medewerker.
- **Cloud** = TF-IDF + Logistic Regression sentiment/urgentie-classifier op de transcripties.

De keten dekt: datapipeline (ETL + validatie + versiebeheer), schaalbaarheid
(PySpark distributed + streaming), modellering (MLflow + Optuna), deployment
(Docker + CI/CD/CT) en monitoring (drift PSI/KS + alerts + Prometheus).

## Runnen

1. `python -m venv .venv && .venv\Scripts\activate`
2. `pip install -r requirements.txt` (of de `%pip install`-regel in de eerste codecel)
3. Open `main.ipynb` → Cell > Run All (top-down, ~5-10 min incl. Spark + Vosk).

Spark op Windows vereist `winutils.exe` + `hadoop.dll` in `%HADOOP_HOME%\bin`
(zie sectie 1.6). De Vosk-NL-modelmap wordt naar `models/vosk-nl/` gedownload als
die ontbreekt.

## Live

- Cloud-API (Render): https://mleops.onrender.com — endpoints `/health`, `/analyze`, `/drift`, `/metrics`
- Edge: Docker-image met offline Vosk-NL ASR (zie sectie 3.6)

## Structuur

Het volledige verslag staat **in** `main.ipynb`:

- Sectie 0 — productvereisten (overzicht, stakeholders, data/model-eisen, scope)
- Sectie 1 — datapipeline + schaalbaarheid (LD1 + LD2)
- Sectie 2 — modellering: edge-ASR + cloud-sentiment (LD3)
- Sectie 3 — deployment: Docker, CI/CD/CT, Render, k8s (LD4)
- Sectie 4 — monitoring: drift, alerts, dashboard (LD5)

`evidence/` bevat read-only exports (HTML-rapporten, referentie-audio); de notebook
zelf is de canonieke bron.

Auteurs: Thomas en Parsa.
