import { StrictMode, useState, useEffect, useRef } from 'react'
import { createRoot } from 'react-dom/client'
import edgeModel from './sentiment_lite.json'
import './index.css'

// VitaCall control panel.
// Default: probeer de cloud-API (FastAPI uit het notebook of serve.py).
// Fallback: lokaal scoren met sentiment_lite.json zodat de medewerker
// nog steeds wat heeft als het netwerk weg is.

const API_URL = 'http://127.0.0.1:8000'

function scoreLocal(text) {
  // TF-IDF + sigmoid in pure JS. Geen netwerk nodig.
  const tokens = (text.toLowerCase().match(/[a-zA-Zàáâäçèéêëìíîïñòóôöùúûü']+/g)) || []
  if (!tokens.length) return null
  const tf = {}
  tokens.forEach(t => { tf[t] = (tf[t] || 0) + 1 })
  let sum = edgeModel.bias
  Object.entries(tf).forEach(([t, count]) => {
    const idx = edgeModel.vocab[t]
    if (idx === undefined) return
    sum += (count / tokens.length) * edgeModel.idf[idx] * edgeModel.coef[idx]
  })
  const proba = 1 / (1 + Math.exp(-sum))
  return {
    sentiment: proba > 0.5 ? 'positief' : 'negatief',
    confidence: Math.max(proba, 1 - proba),
    keywords: findLocalKeywords(text),
  }
}

const URGENT = ['pijn', 'borst', 'benauwd', 'bewusteloos', 'bloed', 'hartaanval',
                'koorts', 'flauwgevallen', 'gevallen', 'niet ademen', 'overdosis']
const MEDS   = ['paracetamol', 'ibuprofen', 'insuline', 'antibiotica', 'medicatie',
                'bloedverdunner', 'inhalator', 'epipen']

function findLocalKeywords(text) {
  const t = text.toLowerCase()
  const out = []
  URGENT.forEach(kw => { if (t.includes(kw)) out.push({ text: kw, type: 'urgentie' }) })
  MEDS  .forEach(kw => { if (t.includes(kw)) out.push({ text: kw, type: 'medicatie' }) })
  return out
}

async function scoreApi(text) {
  // Probeer de FastAPI; verwacht /analyze response shape.
  const r = await fetch(`${API_URL}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!r.ok) throw new Error(`API ${r.status}`)
  return r.json()
}

async function fetchJson(path) {
  const r = await fetch(`${API_URL}${path}`)
  if (!r.ok) throw new Error(`API ${r.status}`)
  return r.json()
}

function App() {
  const [text, setText]         = useState('')
  const [result, setResult]     = useState(null)
  const [history, setHistory]   = useState([])
  const [apiUp, setApiUp]       = useState(false)
  const [metrics, setMetrics]   = useState(null)
  const [drift, setDrift]       = useState(null)
  const [busy, setBusy]         = useState(false)
  const taRef = useRef(null)

  // Elke 5 seconden checken of de API leeft + metrics ophalen.
  useEffect(() => {
    let alive = true
    async function poll() {
      try {
        await fetchJson('/health')
        if (!alive) return
        setApiUp(true)
        const [m, d] = await Promise.all([fetchJson('/metrics'), fetchJson('/drift')])
        if (!alive) return
        setMetrics(m); setDrift(d)
      } catch {
        if (alive) { setApiUp(false); setMetrics(null); setDrift(null) }
      }
    }
    poll()
    const iv = setInterval(poll, 5000)
    return () => { alive = false; clearInterval(iv) }
  }, [])

  async function analyze() {
    if (!text.trim() || busy) return
    setBusy(true)
    let r, source
    try {
      r = await scoreApi(text)
      source = 'cloud'
    } catch {
      r = scoreLocal(text)
      source = 'edge'
    }
    setBusy(false)
    if (!r) return
    setResult({ ...r, source })
    setHistory(h => [
      { id: Date.now(), time: new Date().toTimeString().slice(0,8), text, ...r, source },
      ...h,
    ].slice(0, 20))
    setText('')
    taRef.current?.focus()
  }

  function onKey(e) {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) analyze()
  }

  const urgent = result?.keywords?.some(k => k.type === 'urgentie')

  const isFirstUse = history.length === 0 && !result

  return (
    <div className={`app ${urgent ? 'app-alert' : ''}`}>
      <header className="topbar">
        <h1 className="title">VitaCall</h1>
        <div className="api-status">
          <span className={`dot ${apiUp ? 'dot-up' : 'dot-down'}`}></span>
          {apiUp ? 'Cloud-API verbonden' : 'Offline (edge model)'}
        </div>
      </header>

      {isFirstUse && (
        <div className="onboarding">
          <h2>Welkom bij VitaCall</h2>
          <p>
            Triage-assistent voor de alarmcentrale. Typ wat de beller zegt, en je
            krijgt direct sentiment + spoed-keywords. Werkt online (cloud-API) en
            offline (lokaal edge-model).
          </p>
          <ol>
            <li>Typ of plak de gespreks-tekst hieronder.</li>
            <li>Druk <kbd>Ctrl</kbd>+<kbd>Enter</kbd> of klik op <b>Analyseren</b>.</li>
            <li>Urgentie-keywords kleuren rood; medicatie geel.</li>
            <li>Live monitoring rechts toont latency, drift en uptime van de cloud-API.</li>
          </ol>
          <p className="onboarding-tip">
            Tip: start de cloud-API met <code>uvicorn serve:app</code> in een aparte terminal.
            Zonder API werkt de app ook, maar dan zonder live monitoring.
          </p>
        </div>
      )}

      <main className="grid">
        <section className="panel input-panel">
          <h2>Gesprek invoeren</h2>
          <textarea
            ref={taRef}
            className="input"
            placeholder="Wat zegt de beller? (Ctrl+Enter om te analyseren)"
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={onKey}
            rows={5}
          />
          <button className="submit" onClick={analyze} disabled={!text.trim() || busy}>
            {busy ? 'Bezig...' : 'Analyseren'}
          </button>

          {result && (
            <div className="result">
              <div className="result-row">
                <span className={`pill pill-${result.sentiment}`}>
                  {result.sentiment} ({(result.confidence * 100).toFixed(0)}%)
                </span>
                <span className="source-badge">via {result.source}</span>
              </div>
              <div className="kw-row">
                {result.keywords.length === 0
                  ? <span className="empty">geen keywords</span>
                  : result.keywords.map(k => (
                      <span key={k.text} className={`kw kw-${k.type}`}>{k.text}</span>
                    ))
                }
              </div>
            </div>
          )}
        </section>

        <section className="panel monitor-panel">
          <h2>Live monitoring</h2>
          {metrics ? (
            <div className="stats">
              <div className="stat"><label>Uptime</label><b>{metrics.uptime_s}s</b></div>
              <div className="stat"><label>Requests</label><b>{metrics.requests_total}</b></div>
              <div className="stat"><label>Errors</label><b>{metrics.requests_errors}</b></div>
              <div className="stat"><label>p50</label><b>{metrics.p50_ms} ms</b></div>
              <div className="stat"><label>p95</label><b>{metrics.p95_ms} ms</b></div>
              <div className="stat"><label>Avg conf</label><b>{metrics.avg_confidence}</b></div>
            </div>
          ) : (
            <div className="empty">Wachten op /metrics... start de API met <code>uvicorn serve:app</code></div>
          )}

          {drift && (
            <div className={`drift drift-${drift.status}`}>
              <label>Drift status</label>
              <b>{drift.status}</b>
              <span className="drift-extra">
                positive_rate: {drift.positive_rate} | score: {drift.drift_score} | n: {drift.samples}
              </span>
            </div>
          )}
        </section>

        <section className="panel history-panel">
          <h2>Sessie-log ({history.length})</h2>
          <ul className="history">
            {history.length === 0 && <li className="empty">Nog geen gesprekken</li>}
            {history.map(h => (
              <li key={h.id}>
                <div className="hist-meta">
                  <span className="time">{h.time}</span>
                  <span className={`pill pill-${h.sentiment}`}>{h.sentiment}</span>
                  <span className="source-badge">{h.source}</span>
                </div>
                <p className="hist-text">{h.text}</p>
                <div className="kw-row">
                  {h.keywords.map(k => (
                    <span key={k.text} className={`kw kw-${k.type}`}>{k.text}</span>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  )
}

createRoot(document.getElementById('root')).render(<StrictMode><App /></StrictMode>)
