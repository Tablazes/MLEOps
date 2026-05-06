import { StrictMode, useState, useEffect, useRef } from 'react'
import { createRoot } from 'react-dom/client'
import edgeModel from './sentiment_lite.json'
import './index.css'

// Lokale, offline scoring met de exporteerde TF-IDF + LogReg JSON.
// Geen API call nodig: de Electron app werkt zelfstandig op de laptop
// van de medewerker. Als de cloud-API wel bereikbaar is in 4.x van het
// notebook, kan diezelfde score-logica daar worden hergebruikt.
function scoreSentiment(text) {
  const tokens = text.toLowerCase().match(/[a-zA-Zàáâäçèéêëìíîïñòóôöùúûü']+/g) || []
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
  return { label: proba > 0.5 ? 'positief' : 'negatief', confidence: Math.max(proba, 1 - proba) }
}

const URGENT = ['pijn', 'borst', 'benauwd', 'bewusteloos', 'bloed', 'hartaanval',
                'koorts', 'flauwgevallen', 'gevallen', 'niet ademen', 'overdosis']
const MEDS   = ['paracetamol', 'ibuprofen', 'insuline', 'antibiotica', 'medicatie',
                'bloedverdunner', 'inhalator', 'epipen']

function findKeywords(text) {
  const t = text.toLowerCase()
  const out = []
  URGENT.forEach(kw => { if (t.includes(kw)) out.push({ text: kw, type: 'urgentie' }) })
  MEDS  .forEach(kw => { if (t.includes(kw)) out.push({ text: kw, type: 'medicatie' }) })
  return out
}

function App() {
  const [text, setText]           = useState('')
  const [history, setHistory]     = useState([])
  const [sentiment, setSentiment] = useState(null)
  const [keywords, setKeywords]   = useState([])
  const taRef = useRef(null)

  // Bij elke wijziging van de tekstinvoer: scoor lokaal en update keywords.
  useEffect(() => {
    if (!text.trim()) { setSentiment(null); setKeywords([]); return }
    setSentiment(scoreSentiment(text))
    setKeywords(findKeywords(text))
  }, [text])

  function submit() {
    if (!text.trim()) return
    const entry = {
      id: Date.now(),
      time: new Date().toTimeString().slice(0, 8),
      text,
      sentiment: scoreSentiment(text),
      keywords: findKeywords(text),
    }
    setHistory(h => [entry, ...h].slice(0, 20))
    setText('')
    taRef.current?.focus()
  }

  const urgent = keywords.some(k => k.type === 'urgentie')

  return (
    <div className={`app ${urgent ? 'app-alert' : ''}`}>
      <header className="topbar">
        <h1 className="title">VitaCall - live triage</h1>
        <span className="badge">offline edge model</span>
      </header>

      <main className="panel">
        <textarea
          ref={taRef}
          className="input"
          placeholder="Typ wat de beller zegt..."
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submit() }}
          rows={4}
        />
        <div className="meta">
          {sentiment && (
            <span className={`pill pill-${sentiment.label}`}>
              {sentiment.label} - {(sentiment.confidence * 100).toFixed(0)}%
            </span>
          )}
          {keywords.map(k => (
            <span key={k.text} className={`kw kw-${k.type}`}>{k.text}</span>
          ))}
          <button className="submit" onClick={submit} disabled={!text.trim()}>Loggen</button>
        </div>

        <h2 className="hist-title">Sessie-log ({history.length})</h2>
        <ul className="history">
          {history.length === 0 && <li className="hist-empty">Nog geen gesprekken gelogd</li>}
          {history.map(h => (
            <li key={h.id} className="hist-item">
              <div className="hist-row">
                <span className="hist-time">{h.time}</span>
                <span className={`pill pill-${h.sentiment.label}`}>{h.sentiment.label}</span>
                {h.keywords.map(k => <span key={k.text} className={`kw kw-${k.type}`}>{k.text}</span>)}
              </div>
              <p className="hist-text">{h.text}</p>
            </li>
          ))}
        </ul>
      </main>
    </div>
  )
}

createRoot(document.getElementById('root')).render(<StrictMode><App /></StrictMode>)
