import { StrictMode, useState, useEffect, useRef } from 'react'
import { createRoot } from 'react-dom/client'
import edgeModel from './sentiment_lite.json'
import './index.css'

// ====== Config ======
const API_URL = 'http://127.0.0.1:8000'
const URGENT = ['pijn', 'borst', 'benauwd', 'bewusteloos', 'bloed', 'hartaanval',
                'koorts', 'flauwgevallen', 'gevallen', 'niet ademen', 'overdosis']
const MEDS = ['paracetamol', 'ibuprofen', 'insuline', 'antibiotica', 'medicatie',
              'bloedverdunner', 'inhalator', 'epipen']

// ====== Scoring ======
function scoreLocal(text) {
  const tokens = (text.toLowerCase().match(/[a-zàáâäçèéêëìíîïñòóôöùúûü']+/g)) || []
  if (!tokens.length) return null
  const tf = {}
  tokens.forEach(t => { tf[t] = (tf[t] || 0) + 1 })
  let sum = edgeModel.bias
  Object.entries(tf).forEach(([t, c]) => {
    const i = edgeModel.vocab[t]
    if (i !== undefined) sum += (c / tokens.length) * edgeModel.idf[i] * edgeModel.coef[i]
  })
  const p = 1 / (1 + Math.exp(-sum))
  return { sentiment: p > 0.5 ? 'positief' : 'negatief', confidence: Math.max(p, 1 - p) }
}

function findKeywords(text) {
  const t = text.toLowerCase()
  return [
    ...URGENT.filter(k => t.includes(k)).map(k => ({ text: k, type: 'urgentie' })),
    ...MEDS.filter(k => t.includes(k)).map(k => ({ text: k, type: 'medicatie' })),
  ]
}

async function score(text) {
  try {
    const r = await fetch(`${API_URL}/analyze`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })
    if (!r.ok) throw 0
    const d = await r.json()
    return { ...d, source: 'cloud' }
  } catch {
    const local = scoreLocal(text)
    return local ? { ...local, keywords: findKeywords(text), source: 'edge' } : null
  }
}

// ====== Signaling ======
function makeSignal(role) {
  const ch = new BroadcastChannel('vitacall-rtc')
  return {
    send: msg => ch.postMessage({ from: role, ...msg }),
    on: cb => { ch.onmessage = e => { if (e.data.from !== role) cb(e.data) } },
    close: () => ch.close(),
  }
}
const ICE = { iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] }

// ====== Operator (admin in iPhone call-screen stijl) ======
function Operator() {
  const [state, setState] = useState('idle') // idle | incoming | live
  const [caller, setCaller] = useState({ id: '', name: '' })
  const [timer, setTimer] = useState(0)
  const [transcript, setTranscript] = useState([])
  const [keywords, setKeywords] = useState([])
  const [history, setHistory] = useState([]) // afgesloten gesprekken
  const [viewing, setViewing] = useState(null) // gekozen historisch gesprek
  const [apiUp, setApiUp] = useState(false)

  const sigRef = useRef(null)
  const pcRef = useRef(null)
  const audioRef = useRef(null)
  const handlerRef = useRef(null)

  useEffect(() => {
    const sig = makeSignal('operator')
    sigRef.current = sig
    sig.on(async msg => {
      if (msg.type === 'invite') {
        setCaller({ id: msg.callerId, name: msg.callerName })
        setState('incoming')
      } else if (msg.type === 'transcript' && msg.text) {
        const r = await score(msg.text)
        if (!r) return
        const e = { id: Date.now() + Math.random(), time: new Date().toTimeString().slice(0, 5), text: msg.text, ...r }
        setTranscript(t => [...t, e])
        setKeywords(k => {
          const seen = new Set(k.map(x => x.text))
          return [...k, ...r.keywords.filter(x => !seen.has(x.text))]
        })
      } else if (msg.type === 'hangup') {
        endCall()
      } else if (handlerRef.current) {
        handlerRef.current(msg)
      }
    })
    return () => sig.close()
  }, [])

  useEffect(() => {
    let alive = true
    const check = () => fetch(`${API_URL}/health`).then(r => alive && setApiUp(r.ok)).catch(() => alive && setApiUp(false))
    check()
    const iv = setInterval(check, 3000)
    return () => { alive = false; clearInterval(iv) }
  }, [])

  useEffect(() => {
    if (state !== 'live') return
    const iv = setInterval(() => setTimer(t => t + 1), 1000)
    return () => clearInterval(iv)
  }, [state])

  async function accept() {
    const sig = sigRef.current
    const pc = new RTCPeerConnection(ICE)
    pcRef.current = pc
    const local = await navigator.mediaDevices.getUserMedia({ audio: true }).catch(() => null)
    if (local) local.getTracks().forEach(t => pc.addTrack(t, local))
    pc.ontrack = e => {
      const a = audioRef.current
      if (a) { a.srcObject = e.streams[0]; a.play().catch(() => {}) }
      setState('live'); setTimer(0)
    }
    pc.onicecandidate = e => e.candidate && sig.send({ type: 'ice', candidate: e.candidate })
    handlerRef.current = async msg => {
      if (msg.type === 'offer') {
        await pc.setRemoteDescription(msg.sdp)
        const ans = await pc.createAnswer()
        await pc.setLocalDescription(ans)
        sig.send({ type: 'answer', sdp: ans })
      } else if (msg.type === 'ice' && msg.candidate) {
        try { await pc.addIceCandidate(msg.candidate) } catch {}
      }
    }
    sig.send({ type: 'accept' })
  }

  function endCall() {
    handlerRef.current = null
    if (pcRef.current) { try { pcRef.current.close() } catch {}; pcRef.current = null }
    if (sigRef.current) sigRef.current.send({ type: 'hangup' })
    if (transcript.length > 0 || caller.name) {
      setHistory(h => [{
        id: Date.now(),
        time: new Date().toTimeString().slice(0, 5),
        callerName: caller.name || 'Beller',
        callerId: caller.id,
        duration: timer,
        urgent: keywords.some(k => k.type === 'urgentie'),
        transcript: [...transcript],
        keywords: [...keywords],
      }, ...h].slice(0, 20))
    }
    setState('idle'); setTimer(0); setTranscript([]); setKeywords([])
    setCaller({ id: '', name: '' })
  }

  function decline() {
    if (sigRef.current) sigRef.current.send({ type: 'decline' })
    setState('idle'); setCaller({ id: '', name: '' })
  }

  const fmtTime = `${String(Math.floor(timer / 60)).padStart(2,'0')}:${String(timer % 60).padStart(2,'0')}`
  const lastCall = history[0]
  const sub = state === 'live' ? fmtTime
            : state === 'incoming' ? 'inkomend'
            : lastCall ? `laatste oproep ${lastCall.time}`
            : 'systeem klaar, geen actieve melding'
  const urgent = keywords.some(k => k.type === 'urgentie')

  const posPct = transcript.length ? Math.round(transcript.filter(t => t.sentiment === 'positief').length / transcript.length * 100) : 0
  const negPct = transcript.length ? 100 - posPct : 0
  const avgConf = transcript.length ? Math.round(transcript.reduce((a,t) => a + (t.confidence || 0), 0) / transcript.length * 100) : 0
  const urgentCount = keywords.filter(k => k.type === 'urgentie').length
  const medCount = keywords.filter(k => k.type === 'medicatie').length

  return (
    <div className={`shell ${urgent ? 'urgent' : ''}`}>
      {viewing && (
        <div className="modal-bg" onClick={() => setViewing(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-head">
              <div>
                <h2>{viewing.callerName}</h2>
                <p className="modal-sub">{viewing.time} · {Math.floor(viewing.duration/60)}:{String(viewing.duration%60).padStart(2,'0')} · {viewing.transcript?.length || 0} fragmenten {viewing.urgent && <span className="q-tag">urgentie</span>}</p>
              </div>
              <button className="modal-close" onClick={() => setViewing(null)}><XIcon /></button>
            </div>
            <div className="modal-body">
              {viewing.transcript?.length === 0 ? (
                <p className="dim">Geen transcript opgenomen</p>
              ) : (
                viewing.transcript?.map(m => (
                  <div key={m.id} className={`row r-${m.sentiment}`}>
                    <p>{m.text}</p>
                    <div className="row-meta">
                      <span>{m.time}</span>
                      <span>·</span>
                      <span>{m.sentiment}</span>
                      {m.keywords?.length > 0 && (
                        <>
                          <span>·</span>
                          <span className="kw-inline">
                            {m.keywords.map(k => (
                              <span key={k.text} className={`kw-${k.type}`}>{k.text}</span>
                            ))}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* LINKS: Analyse */}
      <aside className="admin admin-left">
        <div className="admin-section">
          <h3>Stemming</h3>
          {transcript.length === 0 ? (
            <p className="admin-empty">Wacht op gesprek</p>
          ) : (<>
            <div className="bar">
              <div className="bar-pos" style={{ width: `${posPct}%` }} />
              <div className="bar-neg" style={{ width: `${negPct}%` }} />
            </div>
            <div className="admin-grid">
              <div><label>positief</label><b className="g">{posPct}%</b></div>
              <div><label>negatief</label><b className="r">{negPct}%</b></div>
              <div><label>fragmenten</label><b>{transcript.length}</b></div>
              <div><label>zekerheid</label><b>{avgConf}%</b></div>
            </div>
          </>)}
        </div>

        <div className="admin-section">
          <h3>Signalen</h3>
          {keywords.length === 0 ? (
            <p className="admin-empty">Nog geen signalen</p>
          ) : (
            <ul className="admin-kws">
              {keywords.map(k => (
                <li key={k.text} className={`k-${k.type}`}>
                  <span className={`dot d-${k.type}`} />
                  <span className="kt">{k.text}</span>
                  <span className="ky">{k.type}</span>
                </li>
              ))}
            </ul>
          )}
          <div className="admin-grid two">
            <div><label>urgentie</label><b className={urgentCount ? 'r' : ''}>{urgentCount}</b></div>
            <div><label>medicatie</label><b className={medCount ? 'a' : ''}>{medCount}</b></div>
          </div>
        </div>
      </aside>

      {/* MIDDEN: Call + transcript + recente oproepen */}
      <section className="call">
        <div className="topbar">
          <span className="brand">VitaCall <small>alarmcentrale</small></span>
          <span className={`live-pill ${apiUp ? 'on' : 'off'}`}>{apiUp ? 'verbonden' : 'offline'}</span>
        </div>

        <div className="hero">
          <h1 className="caller-name">{state === 'idle' ? 'Geen actieve oproep' : (caller.name || 'Beller')}</h1>
          <div className="caller-sub">{sub}</div>
        </div>

        {/* Live transcript (alleen tijdens of na gesprek) */}
        {(state === 'live' || transcript.length > 0) && (
          <div className="transcript">
            {transcript.length === 0 && <p className="dim">Wachten op spraak…</p>}
            {transcript.map(m => (
              <div key={m.id} className={`row r-${m.sentiment}`}>
                <p>{m.text}</p>
                <div className="row-meta">
                  <span>{m.time}</span>
                  <span>·</span>
                  <span>{m.sentiment}</span>
                  {m.keywords?.length > 0 && (
                    <>
                      <span>·</span>
                      <span className="kw-inline">
                        {m.keywords.map(k => (
                          <span key={k.text} className={`kw-${k.type}`}>{k.text}</span>
                        ))}
                      </span>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Recente oproepen wachtrij (alleen idle) */}
        {state === 'idle' && (
          <div className="queue">
            <h3>Recente oproepen</h3>
            {history.length === 0 ? (
              <p className="dim">Nog geen oproepen vandaag</p>
            ) : (
              <ul className="q-list">
                {history.map(h => (
                  <li key={h.id} className={`q-item ${h.urgent ? 'urg' : ''}`} onClick={() => setViewing(h)}>
                    <span className="q-time">{h.time}</span>
                    <span className="q-name">{h.callerName}</span>
                    <span className="q-dur">{Math.floor(h.duration/60)}:{String(h.duration%60).padStart(2,'0')}</span>
                    {h.urgent && <span className="q-tag">urgentie</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Knoppen ALTIJD onderaan, centraal en groot */}
        <div className="actions">
          {state === 'incoming' && (<>
            <CircleBtn variant="decline" label="Weigeren" onClick={decline}><XIcon /></CircleBtn>
            <CircleBtn variant="accept" label="Aannemen" onClick={accept}><PhoneIcon /></CircleBtn>
          </>)}
          {state === 'live' && (
            <CircleBtn variant="end" label="Beëindigen" onClick={endCall}><XIcon /></CircleBtn>
          )}
          {state === 'idle' && (
            <div className="idle-btn">
              <PhoneIcon /> <span>Wacht op binnenkomende oproep</span>
            </div>
          )}
        </div>

        <audio ref={audioRef} autoPlay playsInline />
      </section>
    </div>
  )
}

// ====== Mobile (caller, iPhone call) ======
function Mobile() {
  const [state, setState] = useState('idle')
  const [timer, setTimer] = useState(0)
  const [error, setError] = useState('')
  const [holdProgress, setHoldProgress] = useState(0)
  const sigRef = useRef(null)
  const pcRef = useRef(null)
  const audioRef = useRef(null)
  const recRef = useRef(null)
  const localRef = useRef(null)
  const holdRef = useRef(null)
  const holdStartRef = useRef(0)

  useEffect(() => {
    if (state !== 'live') return
    const iv = setInterval(() => setTimer(t => t + 1), 1000)
    return () => clearInterval(iv)
  }, [state])

  function startSTT(sig) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) return
    const r = new SR()
    r.lang = 'nl-NL'; r.continuous = true; r.interimResults = false
    r.onresult = e => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript.trim()
        if (e.results[i].isFinal && t) sig.send({ type: 'transcript', text: t })
      }
    }
    r.onend = () => recRef.current === r && r.start()
    try { r.start(); recRef.current = r } catch {}
  }

  async function call() {
    setError(''); setState('calling')
    const local = await navigator.mediaDevices.getUserMedia({ audio: true }).catch(e => { setError(e.message); setState('idle'); return null })
    if (!local) return
    localRef.current = local
    const sig = makeSignal('caller')
    sigRef.current = sig
    const pc = new RTCPeerConnection(ICE)
    pcRef.current = pc
    local.getTracks().forEach(t => pc.addTrack(t, local))
    pc.ontrack = e => {
      const a = audioRef.current
      if (a) { a.srcObject = e.streams[0]; a.play().catch(() => {}) }
      setState('live'); setTimer(0)
    }
    pc.onicecandidate = e => e.candidate && sig.send({ type: 'ice', candidate: e.candidate })
    sig.on(async msg => {
      if (msg.type === 'accept') {
        setState('ringing')
        const offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        sig.send({ type: 'offer', sdp: offer })
        startSTT(sig)
      } else if (msg.type === 'decline') { setError('afgewezen'); hangup() }
      else if (msg.type === 'answer') { await pc.setRemoteDescription(msg.sdp) }
      else if (msg.type === 'ice' && msg.candidate) { try { await pc.addIceCandidate(msg.candidate) } catch {} }
      else if (msg.type === 'hangup') hangup()
    })
    sig.send({ type: 'invite', callerId: `#${Math.floor(Math.random() * 9000) + 1000}`, callerName: 'Beller' })
  }

  function hangup() {
    if (recRef.current) { try { recRef.current.stop() } catch {}; recRef.current = null }
    if (sigRef.current) { sigRef.current.send({ type: 'hangup' }); sigRef.current.close(); sigRef.current = null }
    if (pcRef.current) { try { pcRef.current.close() } catch {}; pcRef.current = null }
    if (localRef.current) { localRef.current.getTracks().forEach(t => t.stop()); localRef.current = null }
    setState('idle'); setTimer(0)
  }

  const fmt = `${String(Math.floor(timer/60)).padStart(2,'0')}:${String(timer%60).padStart(2,'0')}`
  const sub = state === 'live' ? fmt : state === 'calling' ? 'verbinden…' : state === 'ringing' ? 'overgaan…' : 'alarmcentrale'

  function startHold() {
    holdStartRef.current = Date.now()
    setHoldProgress(0)
    holdRef.current = setInterval(() => {
      const elapsed = Date.now() - holdStartRef.current
      const pct = Math.min(elapsed / 2000, 1)
      setHoldProgress(pct)
      if (pct >= 1) {
        cancelHold()
        call()
      }
    }, 50)
  }

  function cancelHold() {
    if (holdRef.current) { clearInterval(holdRef.current); holdRef.current = null }
    setHoldProgress(0)
  }

  const endHoldRef = useRef(null)
  const endHoldStartRef = useRef(0)
  const [endProgress, setEndProgress] = useState(0)

  function startEndHold() {
    endHoldStartRef.current = Date.now()
    setEndProgress(0)
    endHoldRef.current = setInterval(() => {
      const elapsed = Date.now() - endHoldStartRef.current
      const pct = Math.min(elapsed / 2000, 1)
      setEndProgress(pct)
      if (pct >= 1) {
        cancelEndHold()
        hangup()
      }
    }, 50)
  }

  function cancelEndHold() {
    if (endHoldRef.current) { clearInterval(endHoldRef.current); endHoldRef.current = null }
    setEndProgress(0)
  }

  return (
    <div className="mob">
      <div className="mob-top">
        <span className="brand">VitaCall</span>
        <small> alarmcentrale</small>
      </div>
      <div className="mob-hero">
        <h1 className="mob-title">{state === 'live' ? 'In gesprek' : state === 'calling' || state === 'ringing' ? 'Verbinden' : 'Hulp nodig?'}</h1>
        <p className="mob-sub">{sub}</p>
        {state === 'idle' && (
          <p className="mob-info">Verbonden met centrale<br/>Gemiddelde wachttijd: 12 seconden</p>
        )}
      </div>
      {error && <p className="err">{error}</p>}
      <div className="mob-actions">
        {state === 'idle' ? (
          <div className="mob-call-wrap">
            <button
              className="mob-call-btn"
              onMouseDown={startHold}
              onMouseUp={cancelHold}
              onMouseLeave={cancelHold}
              onTouchStart={startHold}
              onTouchEnd={cancelHold}
            >
              <span className="mob-call-ring" style={{ '--p': holdProgress }} />
              <span className="mob-call-icon"><PhoneIcon /></span>
              <span className="mob-call-label">{holdProgress > 0 ? 'Houd vast…' : 'Bellen'}</span>
            </button>
            <span className="mob-call-hint">Houd 2 seconden vast</span>
          </div>
        ) : (
          <div className="mob-call-wrap">
            <button
              className="mob-call-btn mob-end"
              onMouseDown={startEndHold}
              onMouseUp={cancelEndHold}
              onMouseLeave={cancelEndHold}
              onTouchStart={startEndHold}
              onTouchEnd={cancelEndHold}
            >
              <span className="mob-call-ring" style={{ '--p': endProgress }} />
              <span className="mob-call-icon"><XIcon /></span>
              <span className="mob-call-label">{endProgress > 0 ? 'Houd vast…' : 'Ophangen'}</span>
            </button>
            <span className="mob-call-hint">Houd 2 seconden vast</span>
          </div>
        )}
      </div>
      <audio ref={audioRef} autoPlay playsInline />
    </div>
  )
}

// ====== Shared ======
function CircleBtn({ variant, label, onClick, children }) {
  return (
    <button className={`circle ${variant}`} onClick={onClick} aria-label={label}>
      <span className="circle-icon">{children}</span>
      <span className="circle-label">{label}</span>
    </button>
  )
}

const PhoneIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"/>
  </svg>
)
const XIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
    <line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/>
  </svg>
)

// ====== Router ======
function App() {
  const [route, setRoute] = useState(() => {
    const h = window.location.hash.replace('#', '')
    if (h) return h
    if (window.matchMedia?.('(max-width: 760px)').matches) {
      window.location.hash = 'mobile'
      return 'mobile'
    }
    return 'operator'
  })
  useEffect(() => {
    const onHash = () => setRoute(window.location.hash.replace('#', '') || 'operator')
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  return route === 'mobile' ? <Mobile /> : <Operator />
}

createRoot(document.getElementById('root')).render(<StrictMode><App /></StrictMode>)
