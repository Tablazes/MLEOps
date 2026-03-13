import { useState, useEffect, useRef, useCallback } from 'react'

// ── Static data ──
const INITIAL_MESSAGES = [
  { time:'09:14:22', speaker:'medewerker', name:'Medewerker', html:'Goedemiddag, u spreekt met de meldkamer. Waarmee kan ik u helpen?' },
  { time:'09:14:28', speaker:'beller', name:'Beller', html:'Ja hallo, mijn vader heeft <mark class="urgentie">ernstige pijn op de borst</mark> en hij is heel benauwd.' },
  { time:'09:14:35', speaker:'medewerker', name:'Medewerker', html:'Dat klinkt zorgwekkend. Hoe lang heeft hij al deze klachten?' },
  { time:'09:14:41', speaker:'beller', name:'Beller', html:'Ongeveer een half uur nu. Hij gebruikt ook <mark class="medicatie">medicatie</mark>, <mark class="medicatie">bloedverdunners</mark> specifiek.' },
  { time:'09:14:48', speaker:'medewerker', name:'Medewerker', html:'Begrepen. Ik ga direct een ambulance sturen. Kunt u bij hem blijven?' },
  { time:'09:14:54', speaker:'beller', name:'Beller', html:'Ja, ik ben bij hem. Hij zit op de bank en hij zweet heel erg.' },
  { time:'09:15:02', speaker:'medewerker', name:'Medewerker', html:'Goed dat u bij hem bent. De ambulance is onderweg. Heeft hij nog andere <mark class="medicatie">medicatie</mark> gebruikt vandaag?' },
  { time:'09:15:09', speaker:'beller', name:'Beller', html:'Nee, alleen de <mark class="medicatie">bloedverdunners</mark>. Hoe lang duurt het voordat de ambulance er is?' },
  { time:'09:15:16', speaker:'medewerker', name:'Medewerker', html:'De ambulance zou binnen acht minuten bij u moeten zijn. Kunt u mij vertellen of hij bij bewustzijn is?' },
  { time:'09:15:23', speaker:'beller', name:'Beller', html:'Ja hij is bij bewustzijn maar hij klaagt over <mark class="urgentie">druk op de borst</mark> en hij is heel bleek geworden.' },
]

const STREAM_TEMPLATES = [
  {
    speaker: 'medewerker',
    name: 'Medewerker',
    text: 'Blijf bij mij aan de lijn. Kunt u aangeven of de klachten stabiel blijven?',
    html: null,
    kw: [],
  },
  {
    speaker: 'beller',
    name: 'Beller',
    text: 'Hij ademt sneller en zegt dat de druk op de borst toeneemt.',
    html: 'Hij ademt sneller en zegt dat de <mark class="urgentie">druk op de borst</mark> toeneemt.',
    kw: [{ text: 'druk op de borst', type: 'urgentie' }],
  },
  {
    speaker: 'medewerker',
    name: 'Medewerker',
    text: 'Duidelijk, ik noteer dit direct voor het team ter plaatse.',
    html: null,
    kw: [],
  },
  {
    speaker: 'beller',
    name: 'Beller',
    text: 'Hij heeft net nitroglycerine genomen uit zijn medicatiedoosje.',
    html: 'Hij heeft net <mark class="medicatie">nitroglycerine</mark> genomen uit zijn medicatiedoosje.',
    kw: [{ text: 'nitroglycerine', type: 'medicatie' }],
  },
  {
    speaker: 'medewerker',
    name: 'Medewerker',
    text: 'Prima, dank voor de update. Blijft hij aanspreekbaar?',
    html: null,
    kw: [],
  },
  {
    speaker: 'beller',
    name: 'Beller',
    text: 'Ja, maar hij is erg bleek en duizelig.',
    html: 'Ja, maar hij is erg bleek en <mark class="urgentie">duizelig</mark>.',
    kw: [{ text: 'duizelig', type: 'urgentie' }],
  },
  {
    speaker: 'medewerker',
    name: 'Medewerker',
    text: 'Zet indien mogelijk een raam open voor frisse lucht en blijf rustig praten.',
    html: null,
    kw: [],
  },
  {
    speaker: 'beller',
    name: 'Beller',
    text: 'Ik heb zijn actuele medicatielijst klaar liggen voor het team.',
    html: 'Ik heb zijn actuele <mark class="medicatie">medicatielijst</mark> klaar liggen voor het team.',
    kw: [{ text: 'medicatielijst', type: 'medicatie' }],
  },
]

const INITIAL_KEYWORDS = [
  { text:'ernstige pijn op de borst', type:'urgentie' },
  { text:'medicatie', type:'medicatie' },
  { text:'bloedverdunners', type:'medicatie' },
  { text:'druk op de borst', type:'urgentie' },
]

const BARS = Array.from({ length: 44 }, () => ({
  h: 5 + Math.random() * 24,
  dur: (0.35 + Math.random() * 0.55).toFixed(2),
  del: (Math.random() * 0.8).toFixed(2),
}))

function timeToSeconds(time) {
  const [h, m, s] = time.split(':').map(Number)
  return h * 3600 + m * 60 + s
}

function secondsToTime(totalSeconds) {
  const wrapped = ((totalSeconds % 86400) + 86400) % 86400
  const h = Math.floor(wrapped / 3600)
  const m = Math.floor((wrapped % 3600) / 60)
  const s = wrapped % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function buildStreamMessage(idx, timeInSeconds) {
  const template = STREAM_TEMPLATES[idx % STREAM_TEMPLATES.length]
  return {
    ...template,
    time: secondsToTime(timeInSeconds),
  }
}

// ── Typing message component ──
function TypingMessage({ msg, onDone }) {
  const [text, setText] = useState('')
  const [isDone, setIsDone] = useState(false)
  const [showHL, setShowHL] = useState(false)

  useEffect(() => {
    let i = 0
    const iv = setInterval(() => {
      i++
      setText(msg.text.slice(0, i))
      if (i >= msg.text.length) {
        clearInterval(iv)
        setIsDone(true)
        if (msg.html) setTimeout(() => setShowHL(true), 350)
        setTimeout(() => onDone(msg), msg.html ? 500 : 150)
      }
    }, 30)
    return () => clearInterval(iv)
  }, [msg, onDone])

  return (
    <div className="msg msg-new">
      <div className="msg-meta">
        <span className="msg-time">{msg.time}</span>
        <span className={`msg-speaker ${msg.speaker}`}>{msg.name}</span>
      </div>
      {showHL && msg.html ? (
        <p className="msg-text" dangerouslySetInnerHTML={{ __html: msg.html }} />
      ) : (
        <p className="msg-text">
          <span>{text}</span>
          {!isDone && <span className="cursor">{'\u258E'}</span>}
        </p>
      )}
    </div>
  )
}

// ── Main app ──
export default function App() {
  const [messages, setMessages] = useState(INITIAL_MESSAGES)
  const [keywords, setKeywords] = useState(INITIAL_KEYWORDS)
  const [toasts, setToasts] = useState([])
  const [timer, setTimer] = useState(4 * 60 + 32)
  const [currentMsg, setCurrentMsg] = useState(null)
  const [queueIdx, setQueueIdx] = useState(0)
  const [streamTimeSec, setStreamTimeSec] = useState(timeToSeconds(INITIAL_MESSAGES[INITIAL_MESSAGES.length - 1].time))
  const transcriptRef = useRef(null)

  // Timer
  useEffect(() => {
    const iv = setInterval(() => setTimer(t => t + 1), 1000)
    return () => clearInterval(iv)
  }, [])

  const fmtTimer = `${String(Math.floor(timer / 60)).padStart(2, '0')}:${String(timer % 60).padStart(2, '0')}`

  // Auto-scroll (only if near bottom)
  useEffect(() => {
    const el = transcriptRef.current
    if (!el) return
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 100) {
      el.scrollTop = el.scrollHeight
    }
  })

  // Toast helper
  const addToast = useCallback((kw) => {
    const id = Date.now() + Math.random()
    setToasts(prev => [...prev, { ...kw, id, show: false }])
    setTimeout(() => setToasts(prev => prev.map(t => t.id === id ? { ...t, show: true } : t)), 50)
    setTimeout(() => setToasts(prev => prev.map(t => t.id === id ? { ...t, show: false } : t)), 3200)
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3500)
  }, [])

  // Handle typing done
  const handleDone = useCallback((msg) => {
    setMessages(prev => [...prev, { ...msg, html: msg.html || msg.text }])
    setCurrentMsg(null)
    setQueueIdx(prev => prev + 1)
    if (msg.kw?.length) {
      msg.kw.forEach((kw, i) => {
        setTimeout(() => {
          setKeywords(prev => prev.some(k => k.text === kw.text) ? prev : [...prev, { ...kw, isNew: true }])
          addToast(kw)
        }, 500 + i * 400)
      })
    }
  }, [addToast])

  // Schedule next streaming message
  useEffect(() => {
    if (currentMsg !== null) return
    const delay = queueIdx === 0 ? 1400 : 900 + Math.random() * 1400
    const nextTime = streamTimeSec + 6 + Math.floor(Math.random() * 8)
    const t = setTimeout(() => {
      setCurrentMsg(buildStreamMessage(queueIdx, nextTime))
      setStreamTimeSec(nextTime)
    }, delay)
    return () => clearTimeout(t)
  }, [currentMsg, queueIdx, streamTimeSec])

  return (
    <div className="app">
      {/* Sidebar */}
      <aside className="sidebar">
        <button className="sidebar-icon active" title="Gesprek">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z"/>
          </svg>
        </button>
        <button className="sidebar-icon" title="Debug Pipeline">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
            <rect x="4" y="4" width="16" height="16" rx="2"/>
            <line x1="8" y1="9" x2="16" y2="9"/>
            <line x1="8" y1="13" x2="13" y2="13"/>
            <line x1="8" y1="17" x2="11" y2="17"/>
          </svg>
        </button>
      </aside>

      <div className="main">
        {/* Status bar */}
        <div className="status-bar">
          <div className="live-badge"><span className="live-dot" />LIVE</div>
          <span className="timer">{fmtTimer}</span>
          <span className="sep" />
          <span className="caller-info">#4821 · Zuid-Holland</span>
          <span className="status-pill">Medische urgentie</span>
        </div>

        <div className="content-layout">
          {/* Transcript */}
          <div className="transcript" ref={transcriptRef}>
            {messages.map((msg, i) => (
              <div key={i} className="msg">
                <div className="msg-meta">
                  <span className="msg-time">{msg.time}</span>
                  <span className={`msg-speaker ${msg.speaker}`}>{msg.name}</span>
                </div>
                <p className="msg-text" dangerouslySetInnerHTML={{ __html: msg.html }} />
              </div>
            ))}
            {currentMsg && <TypingMessage msg={currentMsg} onDone={handleDone} />}
          </div>

          <aside className="right-stack">
            <div className="panel panel-call">
              <div className="panel-label">Bel-opties</div>
              <div className="waveform">
                {BARS.map((b, i) => (
                  <div
                    key={i}
                    className="bar"
                    style={{ height: `${b.h}px`, animationDuration: `${b.dur}s`, animationDelay: `${b.del}s` }}
                  />
                ))}
              </div>

              <div className="controls">
                <button className="ctrl-btn">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="8" />
                  </svg>
                  Opnemen
                </button>
                <button className="ctrl-btn">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 1a3 3 0 00-3 3v6a3 3 0 006 0V4a3 3 0 00-3-3z"/><path d="M19 10v1a7 7 0 01-14 0v-1"/><line x1="12" y1="18" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/>
                  </svg>
                  Dempen
                </button>
                <button className="ctrl-btn">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                    <rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/>
                  </svg>
                  Wacht
                </button>
                <button className="ctrl-btn ctrl-end">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z"/>
                    <line x1="1" y1="1" x2="23" y2="23"/>
                  </svg>
                  Beëindigen
                </button>
              </div>
            </div>

            <div className="panel panel-keywords">
              <div className="panel-label">Gedetecteerde woorden</div>
              <div className="keywords-list">
                {keywords.map(kw => (
                  <span key={kw.text} className={`kw kw-${kw.type}${kw.isNew ? ' kw-new' : ''}`}>{kw.text}</span>
                ))}
              </div>
            </div>
          </aside>
        </div>
      </div>

      {/* Toast notifications */}
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
