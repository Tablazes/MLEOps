import { useState, useEffect, useRef, useCallback } from 'react'
import { edgeSentiment } from './edgeModel'

const API_URL = 'http://localhost:8000'
const BARS = Array.from({ length: 44 }, () => ({
  h: 5 + Math.random() * 24,
  dur: (0.35 + Math.random() * 0.55).toFixed(2),
  del: (Math.random() * 0.8).toFixed(2),
}))

const timeNow = () => new Date().toTimeString().slice(0, 8)

function highlightKeywords(text, keywords) {
  return keywords.reduce((r, kw) => r.replace(
    new RegExp(`(${kw.text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'),
    `<mark class="${kw.type}">$1</mark>`
  ), text)
}

const API_STATUS_LABEL = { ready: 'Model geladen', loading: 'Model laden...', connecting: 'Verbinden...', offline: 'Offline' }

export default function App() {
  const [messages,        setMessages]        = useState([])
  const [keywords,        setKeywords]        = useState([])
  const [toasts,          setToasts]          = useState([])
  const [timer,           setTimer]           = useState(0)
  const [isListening,     setIsListening]     = useState(false)
  const [isRecording,     setIsRecording]     = useState(false)
  const [isOnHold,        setIsOnHold]        = useState(false)
  const [currentTranscript, setCurrentTranscript] = useState('')
  const [apiStatus,       setApiStatus]       = useState('connecting')
  const [sentiment,       setSentiment]       = useState(null)
  const [manualText,      setManualText]      = useState('')
  const [mwText,          setMwText]          = useState('')
  const transcriptRef  = useRef(null)
  const recognitionRef = useRef(null)
  const wasListeningRef = useRef(false)

  const fmtTimer = `${String(Math.floor(timer / 60)).padStart(2,'0')}:${String(timer % 60).padStart(2,'0')}`

  useEffect(() => {
    const iv = setInterval(() => setTimer(t => t + 1), 1000)
    return () => clearInterval(iv)
  }, [])

  useEffect(() => {
    const check = () =>
      fetch(`${API_URL}/health`).then(r => r.json())
        .then(d => setApiStatus(d.model_loaded ? 'ready' : 'loading'))
        .catch(() => setApiStatus('offline'))
    check()
    const iv = setInterval(check, 5000)
    return () => clearInterval(iv)
  }, [])

  useEffect(() => {
    const el = transcriptRef.current
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 120)
      el.scrollTop = el.scrollHeight
  })

  const addToast = useCallback((kw) => {
    const id = Date.now() + Math.random()
    setToasts(prev => [...prev, { ...kw, id, show: false }])
    setTimeout(() => setToasts(prev => prev.map(t => t.id === id ? { ...t, show: true  } : t)), 50)
    setTimeout(() => setToasts(prev => prev.map(t => t.id === id ? { ...t, show: false } : t)), 3200)
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3500)
  }, [])

  const analyzeText = useCallback(async (text) => {
    if (!text.trim()) return
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
    } catch (e) { console.error('API error:', e); return null }
  }, [apiStatus, addToast])

  const addMsg = useCallback((text, speaker, name, analyze = false) => {
    const id = Date.now()
    setMessages(prev => [...prev, { time: timeNow(), speaker, name, html: text, id }])
    if (analyze)
      analyzeText(text).then(data => {
        if (data?.keywords?.length)
          setMessages(prev => prev.map(m => m.id === id ? { ...m, html: highlightKeywords(text, data.keywords) } : m))
      })
  }, [analyzeText])

  const startListening = useCallback(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) { alert('Speech Recognition niet ondersteund. Gebruik Chrome.'); return }
    const r = new SR()
    r.lang = 'nl-NL'; r.continuous = true; r.interimResults = true
    r.onresult = (e) => {
      let interim = '', final = ''
      for (let i = e.resultIndex; i < e.results.length; i++)
        e.results[i].isFinal ? (final += e.results[i][0].transcript) : (interim = e.results[i][0].transcript)
      if (interim) setCurrentTranscript(interim)
      if (final.trim()) { setCurrentTranscript(''); addMsg(final.trim(), 'beller', 'Beller (ASR)', true) }
    }
    r.onerror = (e) => {
      console.error('Speech error:', e.error)
      if (e.error === 'not-allowed') alert('Microfoontoegang geweigerd.')
    }
    r.onend = () => { if (recognitionRef.current) try { r.start() } catch(e) {} }
    r.start(); recognitionRef.current = r; setIsListening(true)
  }, [addMsg])

  const stopListening = useCallback(() => {
    if (recognitionRef.current) { recognitionRef.current.onend = null; recognitionRef.current.stop(); recognitionRef.current = null }
    setIsListening(false); setCurrentTranscript('')
  }, [])

  const toggleRecording = useCallback(() => {
    if (isRecording) { stopListening(); setIsRecording(false); setIsOnHold(false) }
    else { setIsRecording(true); setIsOnHold(false) }
  }, [isRecording, stopListening])

  const toggleHold = useCallback(() => {
    if (!isRecording) return
    if (isOnHold) { setIsOnHold(false); if (wasListeningRef.current) startListening() }
    else { wasListeningRef.current = isListening; if (isListening) stopListening(); setIsOnHold(true) }
  }, [isOnHold, isListening, isRecording, startListening, stopListening])

  const reset = () => { stopListening(); setMessages([]); setKeywords([]); setSentiment(null); setTimer(0); setIsRecording(false); setIsOnHold(false) }

  return (
    <div className="app">
      <aside className="sidebar">
        <button className="sidebar-icon active" title="Gesprek">
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
          <span className={`api-status api-${apiStatus}`}>API: {API_STATUS_LABEL[apiStatus]}</span>
          {sentiment && (
            <span className={`status-pill ${sentiment.label === 'negatief' ? 'pill-neg' : 'pill-pos'}`}>
              {sentiment.label} ({(sentiment.confidence * 100).toFixed(0)}%)
            </span>
          )}
        </div>

        <div className="content-layout">
          <div className="transcript-area">
            <div className="transcript" ref={transcriptRef}>
              {messages.length === 0 && <div className="empty-state"><p>Geen berichten. Start de microfoon of typ een bericht.</p></div>}
              {messages.map(msg => (
                <div key={msg.id} className="msg msg-new">
                  <div className="msg-meta">
                    <span className="msg-time">{msg.time}</span>
                    <span className={`msg-speaker ${msg.speaker}`}>{msg.name}</span>
                  </div>
                  <p className="msg-text" dangerouslySetInnerHTML={{ __html: msg.html }} />
                </div>
              ))}
              {currentTranscript && (
                <div className="msg msg-interim">
                  <div className="msg-meta">
                    <span className="msg-time">{timeNow()}</span>
                    <span className="msg-speaker beller">Beller (ASR)</span>
                  </div>
                  <p className="msg-text"><span className="interim-text">{currentTranscript}</span><span className="cursor">{'\u258E'}</span></p>
                </div>
              )}
            </div>

            <div className="input-bar">
              {[
                { label: 'Beller:', cls: 'beller',     val: manualText, set: setManualText, placeholder: 'Typ een bericht als beller...',     analyze: true,  name: 'Beller'     },
                { label: 'Mdwrkr:', cls: 'medewerker', val: mwText,     set: setMwText,     placeholder: 'Typ een bericht als medewerker...', analyze: false, name: 'Medewerker' },
              ].map(({ label, cls, val, set, placeholder, analyze, name }) => (
                <div className="input-row" key={cls}>
                  <span className={`input-label ${cls}`}>{label}</span>
                  <input type="text" className="text-input" placeholder={placeholder} value={val}
                    onChange={e => set(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter' && val.trim()) { addMsg(val.trim(), cls, name, analyze); set('') } }}
                  />
                  <button className="send-btn" onClick={() => { if (val.trim()) { addMsg(val.trim(), cls, name, analyze); set('') } }}>Verstuur</button>
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
                <button className={`ctrl-btn ${isRecording ? 'ctrl-active' : ''}`} onClick={toggleRecording}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="8" />
                    {isRecording && <circle cx="12" cy="12" r="4" fill="currentColor" />}
                  </svg>
                  {isRecording ? 'Stop' : 'Opnemen'}
                </button>
                <button className={`ctrl-btn ${isListening ? 'ctrl-active' : ''}`}
                  onClick={() => isListening ? stopListening() : startListening()}
                  disabled={!isRecording || isOnHold}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 1a3 3 0 00-3 3v6a3 3 0 006 0V4a3 3 0 00-3-3z"/><path d="M19 10v1a7 7 0 01-14 0v-1"/><line x1="12" y1="18" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/>
                  </svg>
                  {isListening ? 'Stop ASR' : 'Start ASR'}
                </button>
                <button className={`ctrl-btn ${isOnHold ? 'ctrl-active' : ''}`} onClick={toggleHold} disabled={!isRecording}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                    <rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/>
                  </svg>
                  {isOnHold ? 'Hervat' : 'Wacht'}
                </button>
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
