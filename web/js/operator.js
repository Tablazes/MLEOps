/**
 * VitaCall operator dashboard, web-native port of the Qt OperatorDashboard.
 *
 * Polls backend call state (~400ms) + metrics (~3000ms),
 * renders the live transcript / sentiment / alarms / call panel, drives the
 * accept/end lifecycle buttons, and runs browser Web Speech API STT while the
 * call is active (interim -> postPartial, final -> postTranscript + analyze).
 *
 * @module operator
 */

import {
    getState,
    getMetrics,
    acceptCall,
    endCall,
    analyze,
    postPartial,
    postTranscript,
    startPolling,
    escapeHtml,
} from './api.js';

/* --------------------------------------------------------------------------
   Element handles (ids mirror operator.html)
   -------------------------------------------------------------------------- */
const el = {
    phaseBadge: document.getElementById('phase-badge'),
    offline: document.getElementById('offline'),
    offlineText: document.getElementById('offline-text'),

    statStatus: document.getElementById('stat-status'),
    statDuration: document.getElementById('stat-duration'),
    statUrgentie: document.getElementById('stat-urgentie'),
    statConfidence: document.getElementById('stat-confidence'),

    transcript: document.getElementById('transcript'),
    livePulse: document.getElementById('live-pulse'),
    sttNote: document.getElementById('stt-note'),

    sentimentPos: document.getElementById('sentiment-pos'),
    sentimentPct: document.getElementById('sentiment-pct'),
    sentimentPosLabel: document.getElementById('sentiment-pos-label'),
    sentimentNegLabel: document.getElementById('sentiment-neg-label'),

    alarms: document.getElementById('alarms'),

    callpanel: document.getElementById('callpanel'),
    callpanelPhase: document.getElementById('callpanel-phase'),
    callpanelName: document.getElementById('callpanel-name'),
    callpanelSub: document.getElementById('callpanel-sub'),
    btnAccept: document.getElementById('btn-accept'),
    btnEnd: document.getElementById('btn-end'),

    metricP50: document.getElementById('metric-p50'),
    metricError: document.getElementById('metric-error'),

    analyseContent: document.getElementById('analyse-content'),
    analyseEmpty: document.getElementById('analyse-empty'),
};

/* --------------------------------------------------------------------------
   Dutch keyword fallback (mirrors backend lists), used when analyze() fails
   -------------------------------------------------------------------------- */
const URGENTIE_WOORDEN = [
    'pijn op de borst', 'benauwd', 'bewusteloos', 'gevallen', 'koorts',
    'bloeding', 'hartaanval',
];
const MEDICATIE_WOORDEN = [
    'paracetamol', 'insuline', 'bloedverdunner', 'inhalator', 'epipen',
];

/* --------------------------------------------------------------------------
   Mutable view state
   -------------------------------------------------------------------------- */
const state = {
    phase: 'idle',
    callId: null,
    startedAt: 0,
    renderedCount: 0,      // number of backend events already rendered
    posCount: 0,
    negCount: 0,
    urgentieHits: 0,
    confidenceSum: 0,
    confidenceN: 0,
    busyAccept: false,
    busyEnd: false,
    durationTimer: null,
};

/* --------------------------------------------------------------------------
   Speech recognition (Web Speech API) wiring
   -------------------------------------------------------------------------- */
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let recognising = false;
let recogWanted = false;   // we want STT running (phase === active)

/** Build a single recognition instance configured for Dutch continuous STT. */
function buildRecognition() {
    if (!SpeechRecognition) return null;
    const rec = new SpeechRecognition();
    rec.lang = 'nl-NL';
    rec.continuous = true;
    rec.interimResults = true;

    rec.onresult = (event) => {
        let interim = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
            const res = event.results[i];
            const text = res[0].transcript.trim();
            if (!text) continue;
            if (res.isFinal) {
                postTranscript(text).catch(() => {});
            } else {
                interim += (interim ? ' ' : '') + text;
            }
        }
        if (interim) {
            postPartial(interim).catch(() => {});
        }
    };

    // Auto-restart on natural end / no-speech while we still want it active.
    rec.onend = () => {
        recognising = false;
        if (recogWanted) {
            try {
                rec.start();
                recognising = true;
            } catch {
                /* will retry on next phase tick */
            }
        }
    };

    // Puls pas aan zodra de mic echt luistert (niet alleen omdat phase=active).
    rec.onstart = () => { recognising = true; setPulse(true); hideSttNote(); };
    rec.onaudiostart = () => { setPulse(true); };

    rec.onerror = (e) => {
        setPulse(false);
        const err = e && e.error;
        if (err === 'not-allowed' || err === 'service-not-allowed') {
            recogWanted = false;
            showSttNote('Microfoon geweigerd, geef toestemming in de browser.');
        } else if (err === 'no-speech') {
            showSttNote('Geen spraak gehoord, praat in de microfoon.');
        } else if (err === 'audio-capture') {
            recogWanted = false;
            showSttNote('Geen microfoon gevonden.');
        } else if (err) {
            showSttNote(`Spraakherkenning fout: ${err}`);
        }
    };

    return rec;
}

/** Toggle de live-puls; weerspiegelt of de mic echt luistert. */
function setPulse(on) {
    el.livePulse.classList.toggle('is-hidden', !on);
}

/** Start STT (idempotent). */
function startStt() {
    if (!SpeechRecognition) {
        setPulse(false);
        showSttNote('Spraakherkenning werkt alleen in Chrome of Edge.');
        return;
    }
    recogWanted = true;
    showSttNote('Microfoon starten…');
    if (!recognition) recognition = buildRecognition();
    if (recognition && !recognising) {
        try {
            recognition.start();
        } catch {
            /* start() throws if already started, ignore */
        }
    }
}

/** Stop STT (idempotent). */
function stopStt() {
    recogWanted = false;
    if (recognition && recognising) {
        try {
            recognition.stop();
        } catch {
            /* ignore */
        }
    }
    recognising = false;
    setPulse(false);
}

/** Show a small dim note next to the transcript title. */
function showSttNote(msg) {
    el.sttNote.textContent = msg;
    el.sttNote.classList.remove('is-hidden');
}
function hideSttNote() {
    el.sttNote.classList.add('is-hidden');
}

/* --------------------------------------------------------------------------
   Formatting helpers
   -------------------------------------------------------------------------- */
function fmtTime(ts) {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString('nl-NL', { hour12: false });
}

function fmtDuration(seconds) {
    const s = Math.max(0, Math.floor(seconds));
    const mm = String(Math.floor(s / 60)).padStart(2, '0');
    const ss = String(s % 60).padStart(2, '0');
    return `${mm}:${ss}`;
}

/* --------------------------------------------------------------------------
   Transcript rendering
   -------------------------------------------------------------------------- */
function clearTranscript() {
    el.transcript.innerHTML = '';
    state.renderedCount = 0;
}

function appendSeparator(callId, ts) {
    const row = document.createElement('div');
    row.className = 'transcript__row';
    const label = `── CALL #${callId} · ${fmtTime(ts)} ──`;
    row.innerHTML =
        `<span class="transcript__text text-dim" style="text-align:center;width:100%">${escapeHtml(label)}</span>`;
    el.transcript.appendChild(row);
}

/**
 * Append one final transcript line and kick off async analysis for sentiment
 * + keyword tags + counters.
 *
 * @param {{ts:number,text:string}} ev - Backend event.
 */
function appendLine(ev) {
    const empty = el.transcript.querySelector('.transcript--empty');
    if (empty) empty.remove();

    const lineNo = state.renderedCount + 1;
    const row = document.createElement('div');
    row.className = 'transcript__row';
    row.dataset.line = String(lineNo);          // anker voor klikbare alarmen
    const time = document.createElement('span');
    time.className = 'transcript__time';
    time.textContent = fmtTime(ev.ts);
    const text = document.createElement('span');
    text.className = 'transcript__text';
    text.innerHTML =
        `<span class="text-dim mono">#${lineNo}</span> ${escapeHtml(ev.text)}`;
    row.appendChild(time);
    row.appendChild(text);
    el.transcript.appendChild(row);

    // Geef de regel + zijn echte tijdstempel mee zodat alarmen synchroon lopen.
    analyzeLine(ev.text, row, lineNo, ev.ts);
}

/** Render/refresh the dim italic partial line at the bottom. */
function renderPartial(partial) {
    let row = el.transcript.querySelector('[data-partial]');
    if (!partial) {
        if (row) row.remove();
        return;
    }
    if (!row) {
        row = document.createElement('div');
        row.className = 'transcript__row';
        row.setAttribute('data-partial', '1');
        row.innerHTML =
            `<span class="transcript__time">…</span>` +
            `<span class="transcript__text transcript__text--partial"></span>`;
        el.transcript.appendChild(row);
    }
    row.querySelector('.transcript__text').textContent = partial;
}

function autoScroll() {
    el.transcript.scrollTop = el.transcript.scrollHeight;
}

/* --------------------------------------------------------------------------
   Analysis: sentiment + keyword tags + counters + alarms
   -------------------------------------------------------------------------- */
async function analyzeLine(rawText, rowNode, lineNo, ts) {
    let result;
    try {
        result = await analyze(rawText);
    } catch {
        result = localScan(rawText);
    }

    // Sentiment counters + sentiment direct in de transcript-regel verweven
    if (result.sentiment === 'positief') {
        state.posCount += 1;
        if (rowNode) rowNode.classList.add('transcript__row--pos');
    } else if (result.sentiment === 'negatief') {
        state.negCount += 1;
        if (rowNode) rowNode.classList.add('transcript__row--neg');
    }

    if (typeof result.confidence === 'number') {
        state.confidenceSum += result.confidence;
        state.confidenceN += 1;
    }

    // Keywords -> alarmen rechts (NIET inline in de transcript; voorkomt
    // dubbele/aaneengeplakte tekst en houdt de transcript schoon).
    const keywords = Array.isArray(result.keywords) ? result.keywords : [];
    for (const kw of keywords) {
        if (kw.type === 'urgentie') state.urgentieHits += 1;
        addAlarm(kw, rawText, lineNo, ts);
    }

    renderSentiment();
    renderStats();
}

/** Local keyword scan fallback when /analyze is unreachable. */
function localScan(text) {
    const lower = String(text).toLowerCase();
    const keywords = [];
    for (const w of URGENTIE_WOORDEN) {
        if (lower.includes(w)) keywords.push({ text: w, type: 'urgentie' });
    }
    for (const w of MEDICATIE_WOORDEN) {
        if (lower.includes(w)) keywords.push({ text: w, type: 'medicatie' });
    }
    // No sentiment model available locally: treat urgentie as negatief signal.
    const sentiment = keywords.some((k) => k.type === 'urgentie') ? 'negatief' : 'positief';
    return { sentiment, confidence: null, keywords };
}

/* --------------------------------------------------------------------------
   Alarms list
   -------------------------------------------------------------------------- */
function clearAlarms() {
    el.alarms.innerHTML = '';
}

function addAlarm(kw, contextText, lineNo, ts) {
    const empty = el.alarms.querySelector('.alarms--empty');
    if (empty) empty.remove();

    const row = document.createElement('div');
    row.className =
        'alarm ' + (kw.type === 'urgentie' ? 'alarm--urgentie' : 'alarm--medicatie');
    if (lineNo != null) row.dataset.line = String(lineNo);
    row.tabIndex = 0;
    row.setAttribute('role', 'button');
    const tag = kw.type === 'urgentie' ? 'URGENT' : 'MEDICATIE';
    // Zelfde tijdstempel als de transcript-regel (synchroon, zelfde stijl).
    const tijd = ts != null ? fmtTime(ts) : '';
    row.innerHTML =
        `<span class="alarm__tag">${tag}</span>` +
        `<span class="alarm__text"><strong>${escapeHtml(kw.text)}</strong>, ${escapeHtml(contextText)}</span>` +
        `<span class="alarm__time">${tijd}</span>`;
    // Klik -> spring naar de gekoppelde transcript-regel + highlight kort.
    const jump = () => focusLine(lineNo);
    row.addEventListener('click', jump);
    row.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); jump(); }
    });
    el.alarms.appendChild(row);
}

/** Scroll de transcript naar regel lineNo en highlight die kort. */
function focusLine(lineNo) {
    if (lineNo == null) return;
    const target = el.transcript.querySelector(`.transcript__row[data-line="${lineNo}"]`);
    if (!target) return;
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    target.classList.remove('transcript__row--flash');
    void target.offsetWidth;  // reflow zodat de animatie opnieuw start
    target.classList.add('transcript__row--flash');
}

/* --------------------------------------------------------------------------
   Sentiment bar + stats
   -------------------------------------------------------------------------- */
function renderSentiment() {
    const total = state.posCount + state.negCount;
    const pct = total === 0 ? 50 : Math.round((state.posCount / total) * 100);
    el.sentimentPos.style.width = `${pct}%`;
    el.sentimentPosLabel.innerHTML = `<span class="dot dot--pos"></span> Positief ${state.posCount}`;
    el.sentimentNegLabel.innerHTML = `<span class="dot dot--neg"></span> Negatief ${state.negCount}`;
    if (el.sentimentPct) {
        el.sentimentPct.textContent = total === 0 ? '- % positief' : `${pct}% positief`;
    }
}

function renderStats() {
    el.statUrgentie.textContent = String(state.urgentieHits);
    el.statUrgentie.classList.toggle('stat__value--neg', state.urgentieHits > 0);

    if (state.confidenceN > 0) {
        const avg = state.confidenceSum / state.confidenceN;
        el.statConfidence.textContent = `${Math.round(avg * 100)}%`;
    } else {
        el.statConfidence.textContent = '-';
    }
}

/* --------------------------------------------------------------------------
   Per-call reset (separator + counters + lists)
   -------------------------------------------------------------------------- */
function resetForCall(callId, startedAt) {
    state.posCount = 0;
    state.negCount = 0;
    state.urgentieHits = 0;
    state.confidenceSum = 0;
    state.confidenceN = 0;
    state.renderedCount = 0;

    clearTranscript();
    clearAlarms();
    renderSentiment();
    renderStats();
}

/** Na een gesprek: alle stats, lijsten en transcript wissen (terug naar leeg). */
function resetAnalyse() {
    state.posCount = 0;
    state.negCount = 0;
    state.urgentieHits = 0;
    state.confidenceSum = 0;
    state.confidenceN = 0;
    state.renderedCount = 0;
    clearTranscript();
    clearAlarms();
    el.statDuration.textContent = '00:00';
    el.statUrgentie.textContent = '0';
    el.statConfidence.textContent = '0%';
    el.sentimentPos.style.width = '50%';
    if (el.sentimentPct) el.sentimentPct.textContent = '0%';
}

/* --------------------------------------------------------------------------
   Duration ticker (mm:ss while active)
   -------------------------------------------------------------------------- */
function startDurationTimer() {
    if (state.durationTimer) return;
    state.durationTimer = setInterval(() => {
        if (state.phase === 'active' && state.startedAt) {
            el.statDuration.textContent = fmtDuration(Date.now() / 1000 - state.startedAt);
        }
    }, 1000);
}

function stopDurationTimer() {
    if (state.durationTimer) {
        clearInterval(state.durationTimer);
        state.durationTimer = null;
    }
}

/* --------------------------------------------------------------------------
   Phase / call panel rendering
   -------------------------------------------------------------------------- */
const PHASE_BADGE = {
    idle: { text: 'WACHT', cls: 'badge badge--idle' },
    ringing: { text: 'BELLEN', cls: 'badge badge--warn' },
    active: { text: 'LIVE', cls: 'badge badge--pos' },
};

const PANEL_CLASS = {
    idle: 'callpanel callpanel--idle',
    ringing: 'callpanel callpanel--ringing',
    active: 'callpanel callpanel--active',
};

const STATUS_LABEL = {
    idle: 'Wachtstand',
    ringing: 'Binnenkomende oproep',
    active: 'In gesprek',
};

function renderPhase(data) {
    const phase = data.phase || 'idle';
    const caller = data.caller || '';

    // Header badge (verborgen op verzoek; status staat in de stats-tegel)
    const badge = PHASE_BADGE[phase] || PHASE_BADGE.idle;
    el.phaseBadge.textContent = badge.text;
    el.phaseBadge.className = badge.cls + ' is-hidden';

    // Stat status
    el.statStatus.textContent = STATUS_LABEL[phase] || 'Wachtstand';

    // Call panel
    el.callpanel.className = PANEL_CLASS[phase] || PANEL_CLASS.idle;
    el.callpanelPhase.textContent = (badge.text === 'WACHT' ? 'Wachtstand' : badge.text);

    if (phase === 'idle') {
        el.callpanelName.textContent = 'Geen actieve oproep';
        el.callpanelSub.textContent = 'Wacht op binnenkomende oproep…';
    } else {
        el.callpanelName.textContent = caller || 'Onbekende beller';
        el.callpanelSub.textContent =
            phase === 'ringing' ? 'Oproep komt binnen, accepteren?' : 'Verbonden, live transcript actief';
    }

    // Buttons
    el.btnAccept.disabled = !(phase === 'ringing') || state.busyAccept;
    el.btnEnd.disabled = (phase === 'idle') || state.busyEnd;

    // Live pulse wordt gestuurd door de echte mic-status (setPulse), niet hier.
    if (phase !== 'active') setPulse(false);

    // Analyse alleen tonen tijdens een gesprek; in idle geen placeholders.
    const live = phase !== 'idle';
    el.analyseContent.classList.toggle('is-hidden', !live);
    el.analyseEmpty.classList.toggle('is-hidden', live);
}

/* --------------------------------------------------------------------------
   Main state-poll handler
   -------------------------------------------------------------------------- */
function onState(data) {
    if (data && data.__offline) {
        setOffline(true);
        return;
    }
    setOffline(false);

    const phase = data.phase || 'idle';
    const newCall = data.call_id != null && data.call_id !== state.callId;

    // New call started -> separator + reset counters.
    if (newCall && phase !== 'idle') {
        state.callId = data.call_id;
        state.startedAt = data.started_at || Date.now() / 1000;
        resetForCall(data.call_id, state.startedAt);
    }
    if (data.started_at) state.startedAt = data.started_at;

    // Phase transition side effects (STT lifecycle).
    if (phase !== state.phase) {
        if (phase === 'active') {
            startStt();
            startDurationTimer();
        } else {
            stopStt();
            hideSttNote();
        }
        if (phase === 'idle') {
            state.callId = null;
            stopDurationTimer();
            resetAnalyse();   // na een gesprek: alle stats + lijsten weg
        }
        state.phase = phase;
    }

    // Render new final events (skip already-rendered ones).
    const events = Array.isArray(data.events) ? data.events : [];
    if (events.length > state.renderedCount) {
        for (let i = state.renderedCount; i < events.length; i++) {
            appendLine(events[i]);
            state.renderedCount = i + 1;
        }
        autoScroll();
    }

    // Interim partial line.
    renderPartial(data.partial || '');
    if (data.partial) autoScroll();

    renderPhase(data);
}

/* --------------------------------------------------------------------------
   Metrics strip
   -------------------------------------------------------------------------- */
function onMetrics(data) {
    if (data && data.__offline) return;  // behoud laatste echte waarden
    if (typeof data.p50_ms === 'number') el.metricP50.textContent = Math.round(data.p50_ms);
    if (typeof data.error_rate === 'number') {
        el.metricError.textContent = `${(data.error_rate * 100).toFixed(1)}%`;
    }
}

/* --------------------------------------------------------------------------
   Offline indicator
   -------------------------------------------------------------------------- */
function setOffline(off) {
    el.offline.classList.toggle('is-offline', off);
    el.offline.classList.toggle('is-online', !off);
    el.offlineText.textContent = off ? 'Offline' : 'Verbonden';
}

/* --------------------------------------------------------------------------
   Button + toggle wiring
   -------------------------------------------------------------------------- */
el.btnAccept.addEventListener('click', async () => {
    if (el.btnAccept.disabled) return;
    state.busyAccept = true;
    el.btnAccept.disabled = true;
    try {
        await acceptCall();
    } catch {
        /* next poll re-syncs phase */
    } finally {
        state.busyAccept = false;
    }
});

el.btnEnd.addEventListener('click', async () => {
    if (el.btnEnd.disabled) return;
    state.busyEnd = true;
    el.btnEnd.disabled = true;
    try {
        await endCall();
    } catch {
        /* next poll re-syncs phase */
    } finally {
        state.busyEnd = false;
    }
});

/* --------------------------------------------------------------------------
   Bootstrap polling
   -------------------------------------------------------------------------- */
startPolling(onState, 400, getState);
startPolling(onMetrics, 3000, getMetrics);
