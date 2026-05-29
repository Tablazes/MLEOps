# VitaCall — LD3 ASR-fix + reproduceerbaarheid + web-frontend

**Datum:** 2026-05-29

## Aanleiding (docent-feedback)

Het edge-model was een verkleinde sentiment-classifier (zelfde data als het cloud-model).
Dat is geen ASR en geen tweede onafhankelijk model. De privacy-redenering klopte, maar de
oplossing hoort een ASR-model op de edge te zijn, niet het sentimentmodel verkleinen.

## Fix (minimale, chirurgische wijzigingen)

- **Edge = Vosk-NL ASR** (audio→tekst, lokaal). Ruwe audio verlaat de instelling nooit; alleen
  geanonimiseerde tekst gaat naar de cloud. Dit is de privacy-oplossing zelf.
- **Cloud = sentiment/urgentie-classifier** (TF-IDF + LogReg). Andere taak, andere data, ander
  artefact. Twee echt onafhankelijke modellen, elk een eigen evaluatie.
- Nieuwe sectie **2.0** (markdown + code) importeert `app/asr.py` en evalueert de ASR:
  WER-metric (Levenshtein op woordniveau, eigen implementatie, geen jiwer), modelgrootte, RTF.
- De oude "lightweight" sentiment-JSON is herbenoemd tot **compacte cloud-variant /
  browser-offline-fallback** — expliciet NIET het edge-model.
- Foutlabels "edge = lite" gecorrigeerd in alle betreffende cellen + README + model_card.

## Nieuwe helper

`app/asr.py` (getest): `EdgeASR` (Vosk-NL bestands-decoder), `word_error_rate`, `evaluate`.

## Eerlijke meting (geen verzonnen cijfers)

- Vosk-NL modelgrootte: **65,6 MB** (gemeten).
- RTF op CPU: **~0,17** (≈6× sneller dan real-time; model laadt in ~0,4 s).
- WER op echte NL-spraak: **nog niet meetbaar** — geen NL-spraakcorpus met referentie in de repo,
  geen offline NL-TTS. De cel rapporteert eerlijk `status="geen_referentie_audio"`. Een echte WER
  volgt door enkele zinnen via de app-microfoon op te nemen als `evidence/<naam>.wav` + `.txt` en
  de cel opnieuw te draaien (de harness berekent dan een echt getal).
- WER-rekenkern geverifieerd: 0.0 (gelijk), 0.25 (1 substitutie op 4), 0.333 (1 insertie op 3).

## Verificatie

- `pyright app/asr.py` → 0 errors.
- ASR-cel los gedraaid → WER-self-test OK, 65,6 MB, eerlijke status.
- **Volledige notebook headless uitgevoerd** (`jupyter nbconvert --execute`):
  **37/37 code-cellen, 0 fouten** → reproduceerbaar (LD3 Level-4). Artefact:
  `evidence/_executed_full.ipynb`, log: `evidence/nbexec_full_2026-05-29.log`.
- Rubric-sweep: 25/25 bewijspunten over LD1–LD5.
- Notebook-markdown ge-humaniseerd (6 cellen, geen code/cijfer-wijzigingen).

## Web-frontend (los verzoek)

Volledige website in `web/` (full-bleed, **geen gradient**, geen avatar-tegels), gemount op de
backend en live op `http://127.0.0.1:8000/` (operator + caller + CSS/JS, alle 200). Launcher:
`serve_web.py`. Qt-`app/widgets.py` ook gradient-vrij gemaakt (solide vulling).
