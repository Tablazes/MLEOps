# VitaCall

[![CI/CD](https://github.com/Tablazes/MLEOps/actions/workflows/cicd.yml/badge.svg)](https://github.com/Tablazes/MLEOps/actions/workflows/cicd.yml)

**Live cloud-API:** https://mleops.onrender.com (Render, Docker, free tier), endpoints `/health`, `/analyze`, `/metrics`, `/metrics-prom`.

Nederlandse alarmcentrale-assistent. Twee onafhankelijke modellen voor binnenkomende gesprekken:

- **Edge (lokaal op de operator-pc): Vosk-NL ASR** zet audio om naar tekst. De ruwe audio verlaat het apparaat nooit; dit is de privacy-oplossing en het edge-model.
- **Cloud: TF-IDF + Logistic Regression** sentiment/urgentie-classifier draait op de ge-de-identificeerde tekst (geen audio). Een los model met een eigen taak, data en evaluatie.

Spoed-keywords + drift-detectie draaien live op de transcript.

## Starten

```powershell
pip install -r requirements.txt
jupyter nbconvert --to notebook --execute main.ipynb   # train modellen + genereer evidence
uvicorn serve:app --host 0.0.0.0 --port 8000           # cloud-API lokaal
```

**Vereiste voor de PySpark-split (Windows):** de datapijplijn gebruikt Spark verplicht
(geen pandas-fallback). Spark schrijft op Windows alleen naar schijf met `winutils.exe`.
Zet `HADOOP_HOME` naar een map met `bin\winutils.exe` + `hadoop.dll` (Hadoop 3.3.x, bv.
via github.com/cdarlint/winutils) voordat je het notebook draait:

```powershell
$env:HADOOP_HOME = "$env:USERPROFILE\hadoop"   # map met bin\winutils.exe
```

Ontbreekt dit, dan stopt de split-cel met een duidelijke `RuntimeError` in plaats van
stilletjes terug te vallen. Op Linux/cloud is alleen een JVM nodig.

Of via Docker (zelfde image lokaal en in productie):

```powershell
docker compose up --build        # api + mlflow + prometheus
```

## Structuur

```
main.ipynb              pipeline + training + deployment + monitoring (alle code)
serve.py                FastAPI productie-service (/health /analyze /drift /metrics)
Dockerfile + docker-compose.yml
k8s/deployment.yaml     alternatief deploy-manifest (2 replicas, liveness/readiness)
.github/workflows/cicd.yml
monitoring/             prometheus scrape-config
evidence/               plots + rapporten (gegenereerd door notebook)
models/vosk-nl/         optioneel lokaal edge ASR-model (gitignored vanwege omvang)
models/sentiment_heavy.pkl
```

## Cijfers (gemeten)

**Edge: Vosk-NL ASR** (audio -> tekst, lokaal):

| Metric | Werkelijk |
|---|---|
| Modelgrootte op schijf | gemeten wanneer `models/vosk-nl/` lokaal aanwezig is |
| Laadtijd | gemeten wanneer het model lokaal aanwezig is |
| RTF (decode-tijd / audio-duur) op CPU | gemeten op toegevoegde referentie-audio |
| WER | inline WER-harness in sectie 2.1; zonder model/README status `model_reference_missing`, zonder referentie-audio geen eigen WER |

Er zit (nog) geen Nederlands spraakcorpus met referentie-transcripties in de repo. Een echte WER krijg je door een paar referentiezinnen op te nemen en die door de WER-harness te halen (geen verzonnen getal).

**Cloud: sentiment/urgentie-classifier** (tekst -> label):

| Metric | Doel | Werkelijk |
|---|---|---|
| Test-accuracy | ≥ 0.85 | 0.871 |
| CV-F1 mean (5-fold) | ≥ 0.80 | 0.848 ± 0.056 |
| Inference p95 | ≤ 50 ms | ~5-15 ms |

## CI/CD/CT

`.github/workflows/cicd.yml` (3 jobs): test, docker-build, retrain (cron zondag 03:00 UTC).

## Stack

Python 3.11, scikit-learn, FastAPI, MLflow, PySpark (optioneel), Optuna, Prometheus.
