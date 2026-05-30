# VitaCall

Nederlandse alarmcentrale-assistent. Twee onafhankelijke modellen voor binnenkomende gesprekken:

- **Edge (lokaal op de operator-pc): Vosk-NL ASR** zet audio om naar tekst. De ruwe audio verlaat het apparaat nooit — dit is de privacy-oplossing en dit is het edge-model.
- **Cloud: TF-IDF + Logistic Regression** sentiment/urgentie-classifier draait op de ge-de-identificeerde tekst (geen audio). Een los model met een eigen taak, data en evaluatie.

Spoed-keywords + drift-detectie draaien live op de transcript.

## Starten

```powershell
pip install -r requirements.txt
jupyter nbconvert --to notebook --execute main.ipynb   # train modellen + genereer evidence
uvicorn serve:app --host 0.0.0.0 --port 8000           # cloud-API lokaal
```

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
models/vosk-nl/         edge ASR-model (Vosk-NL, ~65.6 MB)
models/sentiment_heavy.pkl
```

## Cijfers (gemeten)

**Edge — Vosk-NL ASR** (audio -> tekst, lokaal):

| Metric | Werkelijk |
|---|---|
| Modelgrootte op schijf | 65.6 MB |
| Laadtijd | ~0.4 s |
| RTF (decode-tijd / audio-duur) op CPU | ~0.17 (≈6x sneller dan realtime) |
| WER | gemeten via de inline WER-harness in het notebook (sectie 2.0) op zelf-opgenomen referentiezinnen; zonder referentie-audio status `geen_referentie_audio` |

Er zit (nog) geen Nederlands spraakcorpus met referentie-transcripties in de repo. Een echte WER krijg je door een paar referentiezinnen op te nemen en die door de WER-harness te halen — geen verzonnen getal.

**Cloud — sentiment/urgentie-classifier** (tekst -> label):

| Metric | Doel | Werkelijk |
|---|---|---|
| Test-accuracy | ≥ 0.85 | 0.871 |
| CV-F1 mean (5-fold) | ≥ 0.80 | 0.848 ± 0.056 |
| Inference p95 | ≤ 50 ms | ~5–15 ms |

## CI/CD/CT

`.github/workflows/cicd.yml` (3 jobs): test, docker-build, retrain (cron zondag 03:00 UTC).

## Stack

Python 3.11, scikit-learn, FastAPI, MLflow, PySpark (optioneel), Optuna, Prometheus.
