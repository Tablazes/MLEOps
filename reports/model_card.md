# Model Card - VitaCall sentiment classifier

## Model details
- Familie: TF-IDF (1-2 grams, 5000 features) + Logistic Regression.
- Versie: heavy (cloud, productie) + lite (compacte cloud-variant / offline tekst-fallback).
- Training: 19,799 samples (DBRD recensies + 100x oversampled domein-zinnen).
- Seed: 42. sklearn=1.4.2.

## Bedoeld gebruik
- Tweede paar oren voor VitaCall medewerkers tijdens telefoongesprekken.
- Real-time signaalfunctie: highlight spoed-keywords en sentiment-trend.
- NIET bedoeld als enige beslissingsbron of vervanging van triage door een mens.

## Evaluatie
- Test-set: DBRD test split.
- Heavy: accuracy=0.8697  F1=0.8697.
- Lite (compacte variant): trade-off geaccepteerd voor 6x kleiner pickle; secundair, geen edge-/privacy-model.
- Vergelijking met LinearSVC en MultinomialNB: zie evidence/model_comparison.csv.

## Beperkingen
- Boekenrecensie-Nederlands != alarmcentrale-Nederlands. Met oversampling van
  domein-zinnen mitigeren we dit, maar productie-data is geen vervanging.
- Drift-detectie kijkt naar output-distributie, niet naar input-embeddings.
- Federated learning is gesimuleerd; geen echte multi-site training.

## Ethiek
- Gevoelige domein: foute negatieve voorspelling bij echte spoed kost levens.
  Daarom: alleen ondersteunend, nooit auto-prioritering.
- Privacy: model bevat geen audio of NAW-gegevens, alleen TF-IDF gewichten.
