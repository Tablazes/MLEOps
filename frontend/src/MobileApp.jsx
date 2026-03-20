import { useState, useEffect, useRef } from 'react'

const API_HOST = window.location.hostname || 'localhost'
const WS_URL = `ws://${API_HOST}:8000`
const PHONE_ICON = "M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"
const HANGUP_ICON = "M23.71 16.67C20.66 13.78 16.54 12 12 12 7.46 12 3.34 13.78.29 16.67c-.18.18-.29.43-.29.71 0 .28.11.53.29.71l2.48 2.48c.18.18.43.29.71.29.27 0 .52-.11.7-.28.79-.74 1.69-1.36 2.66-1.85.33-.16.56-.5.56-.9v-3.1C8.69 14.25 10.32 14 12 14s3.31.25 4.8.72v3.1c0 .39.23.74.56.9.98.49 1.87 1.12 2.67 1.85.18.18.43.28.7.28.28 0 .53-.11.71-.29l2.48-2.48c.18-.18.29-.43.29-.71 0-.27-.11-.52-.29-.7z"
const WAVE_BARS = Array.from({ length: 24 }, () => ({
  dur: `${0.3 + Math.random() * 0.5}s`,
  del: `${Math.random() * 0.6}s`,
  h: `${6 + Math.random() * 18}px`,
}))

export default function MobileApp() {
  const [status, setStatus] = useState('idle')
  const [timer, setTimer] = useState(0)
  const [isMuted, setIsMuted] = useState(false)
  const [speechPulse, setSpeechPulse] = useState(false)
  const mediaRef = useRef(null)
  const ctxRef = useRef(null)
  const wsRef = useRef(null)
  const mutedRef = useRef(false)

  const fmt = `${String(Math.floor(timer / 60)).padStart(2, '0')}:${String(timer % 60).padStart(2, '0')}`
  const isActive = status === 'connected' || status === 'hold'

  useEffect(() => {
    if (!isActive) return
    const iv = setInterval(() => setTimer(t => t + 1), 1000)
    return () => clearInterval(iv)
  }, [isActive])

  useEffect(() => {
    if (!speechPulse) return
    const t = setTimeout(() => setSpeechPulse(false), 600)
    return () => clearTimeout(t)
  }, [speechPulse])

  function cleanup() {
    [wsRef, ctxRef].forEach(r => { try { r.current?.close() } catch {} ; r.current = null })
    if (mediaRef.current) { mediaRef.current.getTracks().forEach(t => t.stop()); mediaRef.current = null }
  }

  async function startCall() {
    setStatus('ringing')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true }
      })
      mediaRef.current = stream
      const ws = new WebSocket(`${WS_URL}/mobile-asr`)
      wsRef.current = ws

      ws.onmessage = e => {
        const msg = JSON.parse(e.data)
        if (msg.type === 'connected') setStatus('connected')
        if (msg.type === 'error') { alert(msg.message); endCall() }
        if (msg.type === 'speech_detected') setSpeechPulse(true)
      }
      ws.onclose = () => { if (wsRef.current === ws) endCall() }
      ws.onerror = () => { setStatus('idle'); alert('Kan niet verbinden met de server.') }
      ws.onopen = () => {
        const ctx = new AudioContext({ sampleRate: 16000 })
        ctxRef.current = ctx
        const src = ctx.createMediaStreamSource(stream)
        const proc = ctx.createScriptProcessor(4096, 1, 1)
        proc.onaudioprocess = e => {
          if (ws.readyState !== WebSocket.OPEN || mutedRef.current) return
          const f = e.inputBuffer.getChannelData(0)
          const b = new Int16Array(f.length)
          for (let i = 0; i < f.length; i++) b[i] = Math.max(-32768, Math.min(32767, Math.round(f[i] * 32767)))
          ws.send(b.buffer)
        }
        src.connect(proc)
        proc.connect(ctx.destination)
      }
    } catch {
      setStatus('idle')
      alert('Microfoontoegang geweigerd.')
    }
  }

  function endCall() { cleanup(); setStatus('ended') }

  function toggleMute() {
    const track = mediaRef.current?.getAudioTracks()[0]
    if (!track) return
    const next = !isMuted
    track.enabled = !next
    setIsMuted(next)
    mutedRef.current = next
  }

  return (
    <div className="mobile-app">
      <div className="mobile-status-bar">
        <span className="mobile-carrier">VitaCall</span>
        <span className="mobile-time">{new Date().toLocaleTimeString('nl-NL', { hour: '2-digit', minute: '2-digit' })}</span>
      </div>

      <div className="mobile-caller-section">
        {status === 'idle' && <>
          <div className="mobile-incoming-label">VitaCall Triage</div>
          <div className="mobile-ring-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}><path d={PHONE_ICON}/></svg>
          </div>
          <div className="mobile-caller-name">Bel VitaCall</div>
          <div className="mobile-caller-number">Tik om te verbinden met triage</div>
        </>}

        {status === 'ringing' && <>
          <div className="mobile-incoming-label">Verbinden...</div>
          <div className="mobile-ring-icon ringing">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}><path d={PHONE_ICON}/></svg>
          </div>
          <div className="mobile-caller-name">Triage Lijn</div>
          <div className="mobile-caller-number">Verbinden met server...</div>
        </>}

        {isActive && <>
          <div className={`mobile-active-indicator ${speechPulse ? 'pulse' : ''}`}>
            <div className="mobile-active-dot" />
            {status === 'hold' ? 'IN DE WACHT' : 'VERBONDEN'}
          </div>
          <div className="mobile-timer">{fmt}</div>
          <div className="mobile-caller-name">Triage Lijn</div>
          <div className="mobile-caller-number">VitaCall Centraal</div>
          <div className={`mobile-wave ${status === 'hold' || isMuted ? 'mobile-wave-paused' : ''}`}>
            {WAVE_BARS.map((b, i) => <div key={i} className="mobile-wave-bar" style={{ animationDuration: b.dur, animationDelay: b.del, height: b.h }} />)}
          </div>
        </>}

        {status === 'ended' && <>
          <div className="mobile-incoming-label">Gesprek beëindigd</div>
          <div className="mobile-ring-icon ended">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}><line x1="1" y1="1" x2="23" y2="23"/></svg>
          </div>
          <div className="mobile-timer">{fmt}</div>
          <div className="mobile-caller-number">Gesprek duurde {fmt}</div>
        </>}
      </div>

      <div className="mobile-controls">
        {status === 'idle' &&
          <div className="mobile-answer-row">
            <button className="mobile-btn mobile-btn-answer" onClick={startCall}>
              <svg viewBox="0 0 24 24" fill="currentColor"><path d={PHONE_ICON}/></svg>
            </button>
            <span className="mobile-btn-label">Bellen</span>
          </div>}

        {status === 'ringing' &&
          <div className="mobile-answer-row">
            <div className="mobile-btn mobile-btn-connecting"><div className="mobile-spinner" /></div>
            <span className="mobile-btn-label">Verbinden...</span>
          </div>}

        {isActive && <>
          <div className="mobile-action-grid">
            <div className="mobile-action">
              <button className={`mobile-btn-small ${isMuted ? 'mobile-btn-active' : ''}`} onClick={toggleMute}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  {isMuted
                    ? <><line x1="1" y1="1" x2="23" y2="23"/><path d="M9 9v3a3 3 0 005.12 2.12M15 9.34V4a3 3 0 00-5.94-.6"/><path d="M17 16.95A7 7 0 015 12v-2m14 0v2c0 .76-.12 1.49-.34 2.18"/></>
                    : <><path d="M12 1a3 3 0 00-3 3v6a3 3 0 006 0V4a3 3 0 00-3-3z"/><path d="M19 10v1a7 7 0 01-14 0v-1"/><line x1="12" y1="18" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></>}
                </svg>
              </button>
              <span className="mobile-action-label">{isMuted ? 'Gedempt' : 'Dempen'}</span>
            </div>
            <div className="mobile-action">
              <button className={`mobile-btn-small ${status === 'hold' ? 'mobile-btn-active' : ''}`} onClick={() => setStatus(status === 'hold' ? 'connected' : 'hold')}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
              </button>
              <span className="mobile-action-label">{status === 'hold' ? 'Hervat' : 'Wacht'}</span>
            </div>
            <div className="mobile-action">
              <button className="mobile-btn-small" disabled>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 010 14.14M15.54 8.46a5 5 0 010 7.07"/></svg>
              </button>
              <span className="mobile-action-label">Speaker</span>
            </div>
          </div>
          <div className="mobile-end-row">
            <button className="mobile-btn mobile-btn-end" onClick={endCall}>
              <svg viewBox="0 0 24 24" fill="currentColor"><path d={HANGUP_ICON}/></svg>
            </button>
            <span className="mobile-btn-label mobile-btn-label-end">Beëindigen</span>
          </div>
        </>}

        {status === 'ended' &&
          <div className="mobile-answer-row">
            <button className="mobile-btn mobile-btn-answer" onClick={() => { setTimer(0); setStatus('idle'); setIsMuted(false) }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>
            </button>
            <span className="mobile-btn-label">Opnieuw</span>
          </div>}
      </div>
    </div>
  )
}
