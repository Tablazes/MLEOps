import { useState, useEffect, useRef } from 'react'
import { edgeSentiment } from './edgeModel'

const API_URL = 'http://localhost:8000'
const BARS = Array.from({ length: 44 }, () => ({
  h:   5 + Math.random() * 24,
  dur: (0.35 + Math.random() * 0.55).toFixed(2),
  del: (Math.random() * 0.8).toFixed(2),
}))
const timeNow = () => new Date().toTimeString().slice(0, 8)
const API_LABEL = { ready: 'Model geladen', loading: 'Model laden...', connecting: 'Verbinden...', offline: 'Offline' }

function highlight(text, keywords) {
  return keywords.reduce((r, kw) => r.replace(
    new RegExp(`(${kw.text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'),
    `<mark class="${kw.type}">$1</mark>`
  ), text)
}

export default function App() {
  const [messages,    setMessages]    = useState([])
  const [keywords,    setKeywords]    = useState([])
  const [toasts,      setToasts]      = useState([])
  const [timer,       setTimer]       = useState(0)
  const [isListening, setIsListening] = useState(false)
  const [isRecording, setIsRecording] = useState(false)
  const [isOnHold,    setIsOnHold]    = useState(false)
  const [interim,     setInterim]     = useState('')
  const [apiStatus,   setApiStatus]   = useState('connecting')
  const [sentiment,   setSentiment]   = useState(null)
  const [callerText,  setCallerText]  = useState('')
  const [staffText,   setStaffText]   = useState('')
  const transcriptRef  = useRef(null)
  const recognitionRef = useRef(null)
  const wasListening   = useRef(false)

  const fmtTimer = `${String(Math.floor(timer / 60)).padStart(2,'0')}:${String(timer % 60).padStart(2,'0')}`

  // Timer
  useEffect(() => {
    const iv = setInterval(() => setTimer(t => t + 1), 1000)
    return () => clearInterval(iv)
  }, [])

  // API health check
  useEffect(() => {
    const check = () =>
      fetch(`${API_URL}/health`).then(r => r.json())
        .then(d => setApiStatus(d.model_loaded ? 'ready' : 'loading'))
        .catch(() => setApiStatus('offline'))
    check()
    const iv = setInterval(check, 5000)
    return () => clearInterval(iv)
  }, [])

  // Auto-scroll transcript
  useEffect(() => {
    const el = transcriptRef.current
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 120)
      el.scrollTop = el.scrollHeight
  })

  function addToast(kw) {
    const id = Date.now() + Math.random()
    setToasts(prev => [...prev, { ...kw, id, show: false }])
    setTimeout(() => setToasts(prev => prev.map(t => t.id === id ? { ...t, show: true  } : t)), 50)
    setTimeout(() => setToasts(prev => prev.map(t => t.id === id ? { ...t, show: false } : t)), 3200)
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3500)
  }

  async function analyzeText(text) {
    if (!text.trim()) return null
    if (apiStatus !== 'ready') {
      const e = edgeSentiment(text)
      setSentiment({ label: e.sentiment, confidence: e.confidence })
      return e
    }
    try {
      const data = await fetch(`${API_URL}/analyze`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      }).then(r => r.json())
      setSentiment({ label: data.sentiment, confidence: data.confidence })
      data.keywords?.forEach((kw, i) => setTimeout(() => {
        setKeywords(prev => prev.some(k => k.text === kw.text) ? prev : [...prev, { ...kw, isNew: true }])
        addToast(kw)
      }, 200 + i * 300))
      return data
    } catch { return null }
  }

  function addMsg(text, speaker, name, analyze = false) {
    const id = Date.now()
    setMessages(prev => [...prev, { time: timeNow(), speaker, name, html: text, id }])
    if (analyze)
      analyzeText(text).then(data => {
        if (data?.keywords?.length)
          setMessages(prev => prev.map(m => m.id === id ? { ...m, html: highlight(text, data.keywords) } : m))
      })
  }

  function startListening() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) { alert('Speech Recognition niet ondersteund. Gebruik Chrome.'); return }
    const r = new SR()
    r.lang = 'nl-NL'; r.continuous = true; r.interimResults = true
    r.onresult = (e) => {
      let interim = '', final = ''
      for (let i = e.resultIndex; i < e.results.length; i++)
        e.results[i].isFinal ? (final += e.results[i][0].transcript) : (interim = e.results[i][0].transcript)
      if (interim) setInterim(interim)
      if (final.trim()) { setInterim(''); addMsg(final.trim(), 'beller', 'Beller (ASR)', true) }
    }
    r.onerror = (e) => { if (e.error === 'not-allowed') alert('Microfoontoegang geweigerd.') }
    r.onend   = () => { if (recognitionRef.current) try { r.start() } catch {} }
    r.start(); recognitionRef.current = r; setIsListening(true)
  }

  function stopListening() {
    if (recognitionRef.current) { recognitionRef.current.onend = null; recognitionRef.current.stop(); recognitionRef.current = null }
    setIsListening(false); setInterim('')
  }

  function toggleRecording() {
    if (isRecording) { stopListening(); setIsRecording(false); setIsOnHold(false) }
    else { setIsRecording(true) }
  }

  function toggleHold() {
    if (!isRecording) return
    if (isOnHold) { setIsOnHold(false); if (wasListening.current) startListening() }
    else { wasListening.current = isListening; if (isListening) stopListening(); setIsOnHold(true) }
  }

  function reset() {
    stopListening()
    setMessages([]); setKeywords([]); setSentiment(null)
    setTimer(0); setIsRecording(false); setIsOnHold(false)
  }

  function sendMsg(text, setText, speaker, name, analyze) {
    if (!text.trim()) return
    addMsg(text.trim(), speaker, name, analyze)
    setText('')
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <button className="sidebar-icon active" title="Gesprek" aria-label="Gesprek">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z"/>
          </svg>
        </button>
      </aside>

      <div className="main">
        <div className="status-bar">
          <div className={`live-badge ${isOnHold ? 'hold' : isListening ? '' : 'inactive'}`}>
            <span className={`live-dot ${isOnHold || !isListening ? 'paused' : ''}`} />
            {isOnHold ? 'WACHT' : isListening ? 'LIVE' : 'PAUSED'}
          </div>
          <span className="timer">{fmtTimer}</span>
          <span className="sep" />
          <span className="caller-info">#4821 · Zuid-Holland</span>
          <span className={`api-status api-${apiStatus}`}>API: {API_LABEL[apiStatus]}</span>
          {sentiment && (
            <span className={`status-pill ${sentiment.label === 'negatief' ? 'pill-neg' : 'pill-pos'}`}>
              {sentiment.label} ({(sentiment.confidence * 100).toFixed(0)}%)
            </span>
          )}
        </div>

        <div className="content-layout">
          <div className="transcript-area">
            <div className="transcript" ref={transcriptRef}>
              {messages.length === 0
                ? <div className="empty-state"><p>Geen berichten. Start de microfoon of typ een bericht.</p></div>
                : messages.map(msg => (
                    <div key={msg.id} className="msg msg-new">
                      <div className="msg-meta">
                        <span className="msg-time">{msg.time}</span>
                        <span className={`msg-speaker ${msg.speaker}`}>{msg.name}</span>
                      </div>
                      <p className="msg-text" dangerouslySetInnerHTML={{ __html: msg.html }} />
                    </div>
                  ))
              }
              {interim && (
                <div className="msg msg-interim">
                  <div className="msg-meta">
                    <span className="msg-time">{timeNow()}</span>
                    <span className="msg-speaker beller">Beller (ASR)</span>
                  </div>
                  <p className="msg-text"><span className="interim-text">{interim}</span><span className="cursor">▎</span></p>
                </div>
              )}
            </div>

            <div className="input-bar">
              {[
                { label: 'Beller:',  cls: 'beller',     val: callerText, set: setCallerText, ph: 'Typ een bericht als beller...',     analyze: true  },
                { label: 'Mdwrkr:', cls: 'medewerker', val: staffText,  set: setStaffText,  ph: 'Typ een bericht als medewerker...', analyze: false },
              ].map(({ label, cls, val, set, ph, analyze }) => (
                <div className="input-row" key={cls}>
                  <span className={`input-label ${cls}`}>{label}</span>
                  <input type="text" className="text-input" placeholder={ph} value={val}
                    onChange={e => set(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && sendMsg(val, set, cls, label, analyze)}
                  />
                  <button className="send-btn" onClick={() => sendMsg(val, set, cls, label, analyze)}>Verstuur</button>
                </div>
              ))}
            </div>
          </div>

          <aside className="right-stack">
            <div className="panel panel-call">
              <div className="panel-label">Bel-opties</div>
              <div className={`waveform ${isListening ? '' : 'waveform-paused'}`}>
                {BARS.map((b, i) => (
                  <div key={i} className="bar" style={{ height: `${b.h}px`, animationDuration: `${b.dur}s`, animationDelay: `${b.del}s` }} />
                ))}
              </div>
              <div className="controls">
                {[
                  { label: isRecording ? 'Stop' : 'Opnemen', active: isRecording,  onClick: toggleRecording, icon: <><circle cx="12" cy="12" r="8"/>{isRecording && <circle cx="12" cy="12" r="4" fill="currentColor"/>}</> },
                  { label: isListening ? 'Stop ASR' : 'Start ASR', active: isListening, onClick: () => isListening ? stopListening() : startListening(), disabled: !isRecording || isOnHold,
                    icon: <><path d="M12 1a3 3 0 00-3 3v6a3 3 0 006 0V4a3 3 0 00-3-3z"/><path d="M19 10v1a7 7 0 01-14 0v-1"/><line x1="12" y1="18" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></> },
                  { label: isOnHold ? 'Hervat' : 'Wacht', active: isOnHold, onClick: toggleHold, disabled: !isRecording,
                    icon: <><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></> },
                ].map(({ label, active, onClick, disabled, icon }, i) => (
                  <button key={i} className={`ctrl-btn ${active ? 'ctrl-active' : ''}`} onClick={onClick} disabled={disabled}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">{icon}</svg>
                    {label}
                  </button>
                ))}
                <button className="ctrl-btn ctrl-end" onClick={reset}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z"/>
                    <line x1="1" y1="1" x2="23" y2="23"/>
                  </svg>
                  Reset
                </button>
              </div>
            </div>

            <div className="panel panel-keywords">
              <div className="panel-label">Gedetecteerde woorden</div>
              <div className="keywords-list">
                {keywords.length === 0
                  ? <span className="kw-empty">Nog geen keywords gedetecteerd</span>
                  : keywords.map(kw => <span key={kw.text} className={`kw kw-${kw.type}${kw.isNew ? ' kw-new' : ''}`}>{kw.text}</span>)
                }
              </div>
            </div>
          </aside>
        </div>
      </div>

      <div className="toasts">
        {toasts.map(t => (
          <div key={t.id} className={`toast toast-${t.type}${t.show ? ' show' : ''}`}>
            <div className="toast-label">{t.type === 'urgentie' ? 'Urgentie' : 'Medicatie'} keyword</div>
            <div className="toast-text">&ldquo;{t.text}&rdquo;</div>
          </div>
        ))}
      </div>
    </div>
  )
}
