# Integration audit — frontend ↔ backend contract

Datum: 2026-05-06
Bestanden: `electron/src/App.jsx`, `serve.py`, `main.ipynb` (cell 32 export_to_json), `electron/src/sentiment_lite.json`

## Checklist

1. [OK] **POST /analyze body**
   App.jsx stuurt `JSON.stringify({ text })` (App.jsx:40); serve.py `AnalyzeRequest` verwacht exact `text: str` met `min_length=1, max_length=10_000` (serve.py:113-114). Veldnaam en type matchen.

2. [OK] **Response keys (sentiment / confidence / keywords)**
   serve.py retourneert `AnalyzeResponse(sentiment=str, confidence=float, keywords=list)` (serve.py:117-120, 148-149). App.jsx spreadt response in transcript-entry en leest `m.sentiment`, `t.confidence`, `r.keywords` (App.jsx:43, 88-92, 175-177). Exacte sleutels aanwezig.

3. [OK] **/health endpoint**
   serve.py exposeert `@app.get("/health")` met `{status, model_loaded}` (serve.py:135-137). App.jsx pollt elke 3s en checkt `r.ok` (App.jsx:104-109). Endpoint bestaat, contract volstaat (alleen HTTP 200 wordt gebruikt).

4. [OK] **Edge fallback keys (vocab / idf / coef / bias)**
   Notebook cell 32 `export_to_json` schrijft `vocab`, `idf`, `coef`, `bias`, `classes` (main.ipynb:1459-1464). App.jsx `scoreLocal()` leest `edgeModel.bias/vocab/idf/coef` (App.jsx:19-22). Vier benodigde sleutels matchen; `classes` blijft ongebruikt in JS (geen probleem).

5. [OK] **CORS open voor 127.0.0.1:8000**
   serve.py gebruikt `allow_origins=["*"]` zonder `allow_credentials=True` (serve.py:127-132). App.jsx fetcht zonder `credentials`-optie (App.jsx:38-41). Wildcard accepteert `Origin: null` (file://, sandboxed Electron renderer) én `http://localhost:5173` (Vite). Werkt voor preflight OPTIONS via `allow_methods=["GET","POST"]`.

6. [ISSUE] **BroadcastChannel signaling alleen binnen één browser-context**
   `new BroadcastChannel('vitacall-rtc')` (App.jsx:53) levert alleen messages tussen contexten met dezelfde origin in dezelfde agent cluster (i.p.v. proces). Operator (#operator) en Mobile (#mobile) MOETEN in dezelfde browser-instantie / Electron-app draaien. Cross-device demo onmogelijk; meerdere Electron-windows of dev-server tabs in dezelfde Chrome werken wél. Geen doc-regel die dit expliciet noemt — documentatie nodig in README of demo-script.

## Samenvatting
5 van 6 contractpunten in orde. Eén documentatie-issue: BroadcastChannel-beperking.
