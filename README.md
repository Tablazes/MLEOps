# VitaCall

Nederlandse alarmcentrale-assistent. Beller belt naar operator-dashboard. Twee onafhankelijke modellen:

- **Edge (lokaal op de operator-pc): Vosk-NL ASR** zet audio om naar tekst. De ruwe audio verlaat het apparaat nooit — dit is de privacy-oplossing en dit is het edge-model.
- **Cloud: TF-IDF + Logistic Regression** sentiment/urgentie-classifier draait op de ge-de-identificeerde tekst (geen audio). Een los model met een eigen taak, data en evaluatie.

Spoed-keywords + drift-detectie draaien live op de transcript.

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
app/asr.py              edge ASR: Vosk-NL file-decoder + WER-harness (notebook-eval)
app/signals.py          live mic -> Vosk-NL transcript (AudioBridge)
app/models.py           cloud sentiment scoring + compacte tekst-fallback
app/icons.py            vector-iconen (geen emoji)
app/widgets.py          stijl + custom widgets
start.py                launcher: opent beide vensters
Dockerfile + docker-compose.yml
.github/workflows/cicd.yml
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
| WER | gemeten via `app/asr.evaluate()` op zelf-opgenomen referentiezinnen; zonder referentie-audio status `geen_referentie_audio` |

Er zit (nog) geen Nederlands spraakcorpus met referentie-transcripties in de repo. Een echte WER krijg je door via de app-microfoon een paar referentiezinnen op te nemen en die door de WER-harness te halen — geen verzonnen getal.

**Cloud — sentiment/urgentie-classifier** (tekst -> label):

| Metric | Doel | Werkelijk |
|---|---|---|
| Test-accuracy | ≥ 0.85 | 0.871 |
| CV-F1 mean (5-fold) | ≥ 0.80 | 0.848 ± 0.056 |
| Inference p95 | ≤ 50 ms | ~5–15 ms |

## CI/CD/CT

`.github/workflows/cicd.yml` (3 jobs): test, docker-build, retrain (cron zondag 03:00 UTC).

## Stack

Python 3.11, scikit-learn, FastAPI, MLflow, PySide6, PySpark (optioneel), Optuna, Prometheus.
