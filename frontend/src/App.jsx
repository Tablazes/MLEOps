import { useState, useEffect, useRef } from 'react'
import { edgeSentiment } from './edgeModel'

const API_HOST = window.location.hostname || 'localhost'
const API_URL = `http://${API_HOST}:8000`
const WS_URL = `ws://${API_HOST}:8000`
const IS_MOBILE = window.location.pathname.replace(/\/$/, '').endsWith('/mobile')
const timeNow = () => new Date().toTimeString().slice(0, 8)
const API_LABEL = { ready: 'Model geladen', loading: 'Model laden...', connecting: 'Verbinden...', offline: 'Offline' }
const PHONE_D = "M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"
const HANGUP_D = "M23.71 16.67C20.66 13.78 16.54 12 12 12 7.46 12 3.34 13.78.29 16.67c-.18.18-.29.43-.29.71 0 .28.11.53.29.71l2.48 2.48c.18.18.43.29.71.29.27 0 .52-.11.7-.28.79-.74 1.69-1.36 2.66-1.85.33-.16.56-.5.56-.9v-3.1C8.69 14.25 10.32 14 12 14s3.31.25 4.8.72v3.1c0 .39.23.74.56.9.98.49 1.87 1.12 2.67 1.85.18.18.43.28.7.28.28 0 .53-.11.71-.29l2.48-2.48c.18-.18.29-.43.29-.71 0-.27-.11-.52-.29-.7z"
const BARS = Array.from({ length: 44 }, () => ({ h: 5 + Math.random() * 24, dur: (0.35 + Math.random() * 0.55).toFixed(2), del: (Math.random() * 0.8).toFixed(2) }))
const MBARS = Array.from({ length: 24 }, () => ({ dur: `${0.3 + Math.random() * 0.5}s`, del: `${Math.random() * 0.6}s`, h: `${6 + Math.random() * 18}px` }))

function highlight(text, keywords) {
  return keywords.reduce((r, kw) => r.replace(
    new RegExp(`(${kw.text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'),
    `<mark class="${kw.type}">$1</mark>`
  ), text)
}

function MobileView() {
  const [status, setStatus] = useState('idle')
  const [timer, setTimer] = useState(0)
  const [isMuted, setIsMuted] = useState(false)
  const [pulse, setPulse] = useState(false)
  const mediaRef = useRef(null), ctxRef = useRef(null), wsRef = useRef(null), mutedRef = useRef(false)
  const fmt = `${String(Math.floor(timer / 60)).padStart(2, '0')}:${String(timer % 60).padStart(2, '0')}`
  const isActive = status === 'connected' || status === 'hold'

  useEffect(() => { if (!isActive) return; const iv = setInterval(() => setTimer(t => t + 1), 1000); return () => clearInterval(iv) }, [isActive])
  useEffect(() => { if (!pulse) return; const t = setTimeout(() => setPulse(false), 600); return () => clearTimeout(t) }, [pulse])

  function cleanup() {
    [wsRef, ctxRef].forEach(r => { try { r.current?.close() } catch {} ; r.current = null })
    if (mediaRef.current) { mediaRef.current.getTracks().forEach(t => t.stop()); mediaRef.current = null }
  }

  async function startCall() {
    setStatus('ringing')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true } })
      mediaRef.current = stream
      const ws = new WebSocket(`${WS_URL}/mobile-asr`)
      wsRef.current = ws
      ws.onmessage = e => { const m = JSON.parse(e.data); if (m.type === 'connected') setStatus('connected'); if (m.type === 'error') { alert(m.message); endCall() }; if (m.type === 'speech_detected') setPulse(true) }
      ws.onclose = () => { if (wsRef.current === ws) endCall() }
      ws.onerror = () => { setStatus('idle'); alert('Kan niet verbinden met de server.') }
      ws.onopen = () => {
        const ctx = new AudioContext({ sampleRate: 16000 }); ctxRef.current = ctx
        const src = ctx.createMediaStreamSource(stream), proc = ctx.createScriptProcessor(4096, 1, 1)
        proc.onaudioprocess = e => {
          if (ws.readyState !== WebSocket.OPEN || mutedRef.current) return
          const f = e.inputBuffer.getChannelData(0), b = new Int16Array(f.length)
          for (let i = 0; i < f.length; i++) b[i] = Math.max(-32768, Math.min(32767, Math.round(f[i] * 32767)))
          ws.send(b.buffer)
        }
        src.connect(proc); proc.connect(ctx.destination)
      }
    } catch { setStatus('idle'); alert('Microfoontoegang geweigerd.') }
  }

  function endCall() { cleanup(); setStatus('ended') }
  function toggleMute() { const t = mediaRef.current?.getAudioTracks()[0]; if (!t) return; const n = !isMuted; t.enabled = !n; setIsMuted(n); mutedRef.current = n }

  return (
    <div className="mobile-app">
      <div className="mobile-status-bar">
        <span className="mobile-carrier">VitaCall</span>
        <span className="mobile-time">{new Date().toLocaleTimeString('nl-NL', { hour: '2-digit', minute: '2-digit' })}</span>
      </div>
      <div className="mobile-caller-section">
        {status === 'idle' && <><div className="mobile-incoming-label">VitaCall Triage</div><div className="mobile-ring-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}><path d={PHONE_D}/></svg></div><div className="mobile-caller-name">Bel VitaCall</div><div className="mobile-caller-number">Tik om te verbinden met triage</div></>}
        {status === 'ringing' && <><div className="mobile-incoming-label">Verbinden...</div><div className="mobile-ring-icon ringing"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}><path d={PHONE_D}/></svg></div><div className="mobile-caller-name">Triage Lijn</div><div className="mobile-caller-number">Verbinden met server...</div></>}
        {isActive && <><div className={`mobile-active-indicator ${pulse ? 'pulse' : ''}`}><div className="mobile-active-dot" />{status === 'hold' ? 'IN DE WACHT' : 'VERBONDEN'}</div><div className="mobile-timer">{fmt}</div><div className="mobile-caller-name">Triage Lijn</div><div className="mobile-caller-number">VitaCall Centraal</div><div className={`mobile-wave ${status === 'hold' || isMuted ? 'mobile-wave-paused' : ''}`}>{MBARS.map((b, i) => <div key={i} className="mobile-wave-bar" style={{ animationDuration: b.dur, animationDelay: b.del, height: b.h }} />)}</div></>}
        {status === 'ended' && <><div className="mobile-incoming-label">Gesprek beëindigd</div><div className="mobile-ring-icon ended"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}><line x1="1" y1="1" x2="23" y2="23"/></svg></div><div className="mobile-timer">{fmt}</div><div className="mobile-caller-number">Gesprek duurde {fmt}</div></>}
      </div>
      <div className="mobile-controls">
        {status === 'idle' && <div className="mobile-answer-row"><button className="mobile-btn mobile-btn-answer" onClick={startCall}><svg viewBox="0 0 24 24" fill="currentColor"><path d={PHONE_D}/></svg></button><span className="mobile-btn-label">Bellen</span></div>}
        {status === 'ringing' && <div className="mobile-answer-row"><div className="mobile-btn mobile-btn-connecting"><div className="mobile-spinner" /></div><span className="mobile-btn-label">Verbinden...</span></div>}
        {isActive && <>
          <div className="mobile-action-grid">
            <div className="mobile-action"><button className={`mobile-btn-small ${isMuted ? 'mobile-btn-active' : ''}`} onClick={toggleMute}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>{isMuted ? <><line x1="1" y1="1" x2="23" y2="23"/><path d="M9 9v3a3 3 0 005.12 2.12M15 9.34V4a3 3 0 00-5.94-.6"/><path d="M17 16.95A7 7 0 015 12v-2m14 0v2c0 .76-.12 1.49-.34 2.18"/></> : <><path d="M12 1a3 3 0 00-3 3v6a3 3 0 006 0V4a3 3 0 00-3-3z"/><path d="M19 10v1a7 7 0 01-14 0v-1"/><line x1="12" y1="18" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></>}</svg></button><span className="mobile-action-label">{isMuted ? 'Gedempt' : 'Dempen'}</span></div>
            <div className="mobile-action"><button className={`mobile-btn-small ${status === 'hold' ? 'mobile-btn-active' : ''}`} onClick={() => setStatus(status === 'hold' ? 'connected' : 'hold')}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg></button><span className="mobile-action-label">{status === 'hold' ? 'Hervat' : 'Wacht'}</span></div>
            <div className="mobile-action"><button className="mobile-btn-small" disabled><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 010 14.14M15.54 8.46a5 5 0 010 7.07"/></svg></button><span className="mobile-action-label">Speaker</span></div>
          </div>
          <div className="mobile-end-row"><button className="mobile-btn mobile-btn-end" onClick={endCall}><svg viewBox="0 0 24 24" fill="currentColor"><path d={HANGUP_D}/></svg></button><span className="mobile-btn-label mobile-btn-label-end">Beëindigen</span></div>
        </>}
        {status === 'ended' && <div className="mobile-answer-row"><button className="mobile-btn mobile-btn-answer" onClick={() => { setTimer(0); setStatus('idle'); setIsMuted(false) }}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg></button><span className="mobile-btn-label">Opnieuw</span></div>}
      </div>
    </div>
  )
}

export default function App() {
  if (IS_MOBILE) return <MobileView />

  const [page,        setPage]        = useState('call')
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
  const [drift,       setDrift]       = useState(null)
  const transcriptRef  = useRef(null)
  const recognitionRef = useRef(null)
  const mediaStreamRef = useRef(null)
  const audioCtxRef    = useRef(null)
  const wasListening   = useRef(false)

  const fmtTimer = `${String(Math.floor(timer / 60)).padStart(2,'0')}:${String(timer % 60).padStart(2,'0')}`

  useEffect(() => {
    if (!isRecording) return
    const iv = setInterval(() => setTimer(t => t + 1), 1000)
    return () => clearInterval(iv)
  }, [isRecording])

  useEffect(() => {
    let ws, reconnectTimer, fallbackIv, alive = true
    function connectWs() {
      if (!alive) return
      ws = new WebSocket(`${WS_URL}/ws`)
      ws.onopen = () => { setApiStatus('ready'); if (fallbackIv) { clearInterval(fallbackIv); fallbackIv = null } }
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data)
        if (msg.type === 'status') { setApiStatus(msg.health.model_loaded ? 'ready' : 'loading'); setDrift(msg.drift) }
        if (msg.type === 'analysis') {
          setDrift(msg.drift)
          if (msg.source === 'mobile') {
            setSentiment({ label: msg.sentiment, confidence: msg.confidence })
            msg.keywords?.forEach((kw, i) => setTimeout(() => { setKeywords(prev => prev.some(k => k.text === kw.text) ? prev : [...prev, { ...kw, isNew: true }]); addToast(kw) }, 200 + i * 300))
          }
        }
        if (msg.type === 'mobile_transcript') addMsg(msg.text, 'beller', 'Beller (Mobiel)', true)
        if (msg.type === 'mobile_partial') setInterim(msg.text)
        if (msg.type === 'mobile_connected') { addMsg('Mobiele beller verbonden', 'systeem', 'Systeem', false); if (!isRecording) setIsRecording(true) }
        if (msg.type === 'mobile_disconnected') { addMsg('Mobiele beller verbroken', 'systeem', 'Systeem', false); setInterim('') }
      }
      ws.onclose = () => {
        if (!alive) return
        setApiStatus('connecting')
        reconnectTimer = setTimeout(connectWs, 2000)
        if (!fallbackIv) fallbackIv = setInterval(() => {
          fetch(`${API_URL}/health`).then(r => r.json()).then(d => setApiStatus(d.model_loaded ? 'ready' : 'loading')).catch(() => setApiStatus('offline'))
          fetch(`${API_URL}/drift`).then(r => r.json()).then(d => setDrift(d)).catch(() => {})
        }, 5000)
      }
      ws.onerror = () => ws.close()
    }
    fetch(`${API_URL}/health`).then(r => r.json()).then(d => setApiStatus(d.model_loaded ? 'ready' : 'loading')).catch(() => setApiStatus('offline'))
    fetch(`${API_URL}/drift`).then(r => r.json()).then(d => setDrift(d)).catch(() => {})
    connectWs()
    return () => { alive = false; clearTimeout(reconnectTimer); if (fallbackIv) clearInterval(fallbackIv); if (ws) ws.close() }
  }, [])

  useEffect(() => { const el = transcriptRef.current; if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 120) el.scrollTop = el.scrollHeight })

  function addToast(kw) {
    const id = Date.now() + Math.random()
    setToasts(prev => [...prev, { ...kw, id, show: false }])
    setTimeout(() => setToasts(prev => prev.map(t => t.id === id ? { ...t, show: true } : t)), 50)
    setTimeout(() => setToasts(prev => prev.map(t => t.id === id ? { ...t, show: false } : t)), 3200)
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3500)
  }

  async function analyzeText(text) {
    if (!text.trim()) return null
    if (apiStatus !== 'ready') {
      const e = edgeSentiment(text)
      setSentiment({ label: e.sentiment, confidence: e.confidence })
      const t = text.toLowerCase(), localKws = []
      const kwMap = { urgentie: ["pijn op de borst","borst","benauwd","bewusteloos","bloeding","hartaanval","koorts","niet ademen","gevallen","overdosis","misselijk","hoofdpijn","duizelig","epilepsie"], medicatie: ["medicatie","medicijn","insuline","antibiotica","paracetamol","ibuprofen","bloeddruk","astma","inhalator","allergie","epipen"] }
      for (const [type, words] of Object.entries(kwMap)) for (const w of words) if (t.includes(w)) localKws.push({ text: w, type })
      localKws.forEach((kw, i) => setTimeout(() => { setKeywords(prev => prev.some(k => k.text === kw.text) ? prev : [...prev, { ...kw, isNew: true }]); addToast(kw) }, 200 + i * 300))
      return { ...e, keywords: localKws }
    }
    try {
      const data = await fetch(`${API_URL}/analyze`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) }).then(r => r.json())
      setSentiment({ label: data.sentiment, confidence: data.confidence })
      data.keywords?.forEach((kw, i) => setTimeout(() => { setKeywords(prev => prev.some(k => k.text === kw.text) ? prev : [...prev, { ...kw, isNew: true }]); addToast(kw) }, 200 + i * 300))
      return data
    } catch { return null }
  }

  function addMsg(text, speaker, name, analyze = false) {
    const id = Date.now()
    setMessages(prev => [...prev, { time: timeNow(), speaker, name, html: text, id }])
    if (analyze) analyzeText(text).then(data => { if (data?.keywords?.length) setMessages(prev => prev.map(m => m.id === id ? { ...m, html: highlight(text, data.keywords) } : m)) })
  }

  async function startListening() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true } })
      mediaStreamRef.current = stream
      const ws = new WebSocket(`${WS_URL}/asr`)
      recognitionRef.current = ws
      ws.onmessage = (e) => { const msg = JSON.parse(e.data); if (msg.error) { alert(msg.error); stopListening(); return }; if (msg.type === 'partial') setInterim(msg.text); if (msg.type === 'final') { setInterim(''); addMsg(msg.text, 'beller', 'Beller (ASR)', true) } }
      ws.onclose = () => { if (recognitionRef.current === ws) stopListening() }
      ws.onopen = () => {
        const ctx = new AudioContext({ sampleRate: 16000 }); audioCtxRef.current = ctx
        const source = ctx.createMediaStreamSource(stream), processor = ctx.createScriptProcessor(4096, 1, 1)
        processor.onaudioprocess = (e) => {
          if (ws.readyState !== WebSocket.OPEN) return
          const float32 = e.inputBuffer.getChannelData(0), int16 = new Int16Array(float32.length)
          for (let i = 0; i < float32.length; i++) int16[i] = Math.max(-32768, Math.min(32767, Math.round(float32[i] * 32767)))
          ws.send(int16.buffer)
        }
        source.connect(processor); processor.connect(ctx.destination); setIsListening(true)
      }
    } catch { alert('Microfoontoegang geweigerd of niet beschikbaar.') }
  }

  function stopListening() {
    if (recognitionRef.current) { try { recognitionRef.current.close() } catch {} ; recognitionRef.current = null }
    if (audioCtxRef.current) { try { audioCtxRef.current.close() } catch {} ; audioCtxRef.current = null }
    if (mediaStreamRef.current) { mediaStreamRef.current.getTracks().forEach(t => t.stop()); mediaStreamRef.current = null }
    setIsListening(false); setInterim('')
  }

  function toggleRecording() { if (isRecording) { stopListening(); setIsRecording(false); setIsOnHold(false) } else { setIsRecording(true); startListening() } }
  function toggleHold() { if (!isRecording) return; if (isOnHold) { setIsOnHold(false); if (wasListening.current) startListening() } else { wasListening.current = isListening; if (isListening) stopListening(); setIsOnHold(true) } }

  return (
    <div className="app">
      <aside className="sidebar">
        <button className={`sidebar-icon ${page === 'call' ? 'active' : ''}`} title="Gesprek" aria-label="Gesprek" onClick={() => setPage('call')}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d={PHONE_D}/></svg>
        </button>
        <button className={`sidebar-icon ${page === 'status' ? 'active' : ''}`} title="Status" aria-label="Status" onClick={() => setPage('status')}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 12h2l2-4 2 8 2-4h2"/></svg>
        </button>
      </aside>

      <div className="main">
        {page === 'status' ? (
          <div className="status-page">
            <div className="status-page-header"><h2 className="status-page-title">Systeemstatus</h2><span className="status-page-time">{timeNow()}</span></div>
            <div className="status-grid">
              <div className="status-card"><div className="status-card-header"><span className="status-card-label">API Server</span><span className={`status-dot dot-${apiStatus === 'ready' ? 'green' : apiStatus === 'loading' ? 'amber' : 'red'}`} /></div><div className="status-card-value">{API_LABEL[apiStatus]}</div><div className="status-card-detail">{API_URL}</div></div>
              <div className="status-card"><div className="status-card-header"><span className="status-card-label">Spraakherkenning (ASR)</span><span className={`status-dot dot-${isListening ? 'green' : isRecording ? 'amber' : 'red'}`} /></div><div className="status-card-value">{isListening ? 'Actief — luistert' : isRecording ? 'Opname aan, ASR gestopt' : 'Inactief'}</div><div className="status-card-detail">Taal: nl-NL · Engine: Vosk (lokaal, offline)</div><div className="status-card-actions"><button className={`sc-btn ${isRecording ? 'sc-btn-active' : ''}`} onClick={toggleRecording}>{isRecording ? 'Stop' : 'Start'}</button></div></div>
              <div className="status-card"><div className="status-card-header"><span className="status-card-label">Sentiment Model</span><span className={`status-dot dot-${apiStatus === 'ready' ? 'green' : 'red'}`} /></div><div className="status-card-value">{apiStatus === 'ready' ? 'Cloud model (TF-IDF + LogReg)' : 'Edge fallback (keyword scoring)'}</div><div className="status-card-detail">{sentiment ? `Laatste: ${sentiment.label} (${(sentiment.confidence * 100).toFixed(0)}%)` : 'Nog geen analyse uitgevoerd'}</div></div>
              <div className="status-card"><div className="status-card-header"><span className="status-card-label">Drift Monitor</span><span className={`status-dot dot-${!drift || drift.status === 'onvoldoende_data' ? 'amber' : drift.status === 'normaal' ? 'green' : 'red'}`} /></div><div className="status-card-value">{!drift ? 'Laden...' : drift.status === 'onvoldoende_data' ? 'Onvoldoende data' : drift.status === 'normaal' ? 'Normaal' : 'Drift gedetecteerd'}</div><div className="status-card-detail">{drift ? `Positief: ${(drift.positive_rate * 100).toFixed(1)}% · Score: ${drift.drift_score} · Samples: ${drift.samples}` : '—'}</div></div>
              <div className="status-card"><div className="status-card-header"><span className="status-card-label">Sessie</span><span className={`status-dot dot-${isRecording ? 'green' : 'amber'}`} /></div><div className="status-card-value">{fmtTimer}</div><div className="status-card-detail">{messages.length} berichten · {keywords.length} keywords gedetecteerd</div></div>
              <div className="status-card"><div className="status-card-header"><span className="status-card-label">Keywords</span><span className={`status-dot dot-${keywords.some(k => k.type === 'urgentie') ? 'red' : keywords.length ? 'amber' : 'green'}`} /></div><div className="status-card-value">{keywords.filter(k => k.type === 'urgentie').length} urgentie · {keywords.filter(k => k.type === 'medicatie').length} medicatie</div><div className="status-card-detail">{keywords.length === 0 ? 'Geen keywords' : keywords.map(k => k.text).join(', ')}</div></div>
            </div>
          </div>
        ) : (<>
        <div className="status-bar">
          <div className={`live-badge ${isOnHold ? 'hold' : isListening ? '' : 'inactive'}`}><span className={`live-dot ${isOnHold || !isListening ? 'paused' : ''}`} />{isOnHold ? 'WACHT' : isListening ? 'LIVE' : 'PAUSED'}</div>
          <span className="timer">{fmtTimer}</span><span className="sep" /><span className="caller-info">#4821 · Zuid-Holland</span>
          {sentiment && <span className={`status-pill ${sentiment.label === 'negatief' ? 'pill-neg' : 'pill-pos'}`}>{sentiment.label} ({(sentiment.confidence * 100).toFixed(0)}%)</span>}
        </div>
        <div className="content-layout">
          <div className="transcript-area">
            <div className="transcript" ref={transcriptRef}>
              {messages.length === 0
                ? <div className="empty-state"><p>Geen berichten. Start de microfoon om te beginnen.</p></div>
                : messages.map(msg => <div key={msg.id} className="msg msg-new"><div className="msg-meta"><span className="msg-time">{msg.time}</span><span className={`msg-speaker ${msg.speaker}`}>{msg.name}</span></div><p className="msg-text" dangerouslySetInnerHTML={{ __html: msg.html }} /></div>)}
              {interim && <div className="msg msg-interim"><div className="msg-meta"><span className="msg-time">{timeNow()}</span><span className="msg-speaker beller">Beller (ASR)</span></div><p className="msg-text"><span className="interim-text">{interim}</span><span className="cursor">▎</span></p></div>}
            </div>
          </div>
          <aside className="right-stack">
            <div className="panel panel-call">
              <div className="panel-label">Bel-opties</div>
              <div className={`waveform ${isListening ? '' : 'waveform-paused'}`}>{BARS.map((b, i) => <div key={i} className="bar" style={{ height: `${b.h}px`, animationDuration: `${b.dur}s`, animationDelay: `${b.del}s` }} />)}</div>
              <div className="controls controls-single"><button className={`ctrl-btn ctrl-main ${isRecording ? 'ctrl-active' : ''}`} onClick={toggleRecording}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M12 1a3 3 0 00-3 3v6a3 3 0 006 0V4a3 3 0 00-3-3z"/><path d="M19 10v1a7 7 0 01-14 0v-1"/><line x1="12" y1="18" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>{isRecording ? 'Stop' : 'Start'}</button></div>
            </div>
            <div className="panel panel-keywords"><div className="panel-label">Gedetecteerde woorden</div><div className="keywords-list">{keywords.length === 0 ? <span className="kw-empty">Nog geen keywords gedetecteerd</span> : keywords.map(kw => <span key={kw.text} className={`kw kw-${kw.type}${kw.isNew ? ' kw-new' : ''}`}>{kw.text}</span>)}</div></div>
          </aside>
        </div>
        </>)}
      </div>
      <div className="toasts">{toasts.map(t => <div key={t.id} className={`toast toast-${t.type}${t.show ? ' show' : ''}`}><div className="toast-label">{t.type === 'urgentie' ? 'Urgentie' : 'Medicatie'} keyword</div><div className="toast-text">&ldquo;{t.text}&rdquo;</div></div>)}</div>
    </div>
  )
}
