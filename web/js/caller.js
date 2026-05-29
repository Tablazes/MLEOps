/**
 * VitaCall, caller (beller) screen controller.
 *
 * Phone-like full-screen view: one big circular call button that starts a call
 * when idle and hangs up when ringing/active. Polls the backend every ~400ms to
 * reflect phase, shows a live ticking timer + transcript while connected, and a
 * subtle offline note when the backend is unreachable. Mirrors the Qt
 * CallerScreen behaviour, web-native.
 *
 * @module caller
 */

import { startCall, endCall, startPolling, escapeHtml } from './api.js';

/** Poll interval for call state, in milliseconds. @type {number} */
const POLL_MS = 400;

/** Inline SVG icons (no external assets, no gradient). @type {Record<string,string>} */
const ICONS = {
    // Solid handset, "bel".
    phone:
        '<svg viewBox="0 0 24 24" width="36" height="36" fill="currentColor" aria-hidden="true">' +
        '<path d="M6.6 10.8a15.5 15.5 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.58 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1 11.4 11.4 0 0 0 .57 3.6 1 1 0 0 1-.25 1l-2.22 2.2Z"/>' +
        '</svg>',
    // Handset rotated down, "ophangen".
    phone_down:
        '<svg viewBox="0 0 24 24" width="36" height="36" fill="currentColor" aria-hidden="true">' +
        '<path d="M12 9c-1.7 0-3.4.24-5 .7v3.1a1 1 0 0 1-.55.9l-2.1 1.05a1 1 0 0 1-1.26-.32 12.9 12.9 0 0 1 0-9.86A17.8 17.8 0 0 1 12 3c3.3 0 6.45.78 8.96 2.66a12.9 12.9 0 0 1 0 9.86 1 1 0 0 1-1.26.32l-2.1-1.05a1 1 0 0 1-.55-.9V9.7c-1.6-.46-3.3-.7-5-.7Z"/>' +
        '</svg>',
};

const els = {
    phase: document.getElementById('phase'),
    status: document.getElementById('status'),
    sub: document.getElementById('sub'),
    offline: document.getElementById('offline'),
    offlineText: document.getElementById('offlineText'),
    transcriptCard: document.getElementById('transcriptCard'),
    transcript: document.getElementById('transcript'),
    partial: document.getElementById('partial'),
    callBtn: document.getElementById('callBtn'),
    callLabel: document.getElementById('callLabel'),
};

/** Last phase rendered, so we only react to phase transitions. @type {string} */
let phase = 'idle';
/** Elapsed seconds while active (ticked locally every 1s). @type {number} */
let timerSeconds = 0;
/** Number of transcript events already rendered. @type {number} */
let renderedEvents = 0;
/** True while a start/end request is in flight (debounce). @type {boolean} */
let busy = false;

/**
 * Format seconds as mm:ss.
 *
 * @param {number} total - Elapsed whole seconds.
 * @returns {string} Zero-padded `mm:ss` string.
 */
function mmss(total) {
    const m = Math.floor(total / 60);
    const s = total % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

/**
 * Configure the call button + caption for the current phase.
 *
 * Idle -> green "Bel alarmcentrale" (start). Ringing/active -> red "Ophangen"
 * (end).
 *
 * @param {'idle'|'ringing'|'active'} p - Phase to render the control for.
 * @returns {void}
 */
function renderButton(p) {
    const isIdle = p === 'idle';
    els.callBtn.classList.toggle('caller__callbtn--call', isIdle);
    els.callBtn.classList.toggle('caller__callbtn--hangup', !isIdle);
    els.callBtn.innerHTML = isIdle ? ICONS.phone : ICONS.phone_down;
    const label = isIdle ? 'Bel alarmcentrale' : 'Ophangen';
    els.callLabel.textContent = label;
    els.callBtn.setAttribute('aria-label', label);
}

/**
 * Toggle the call: start when idle, otherwise end. Debounced via `busy`.
 *
 * @returns {Promise<void>}
 */
async function toggleCall() {
    if (busy) return;
    busy = true;
    try {
        if (phase === 'idle') {
            await startCall('Beller');
        } else {
            await endCall();
        }
    } catch {
        showOffline(true);
    } finally {
        busy = false;
    }
}

/**
 * Show or hide the offline note.
 *
 * @param {boolean} on - Whether the backend is currently unreachable.
 * @returns {void}
 */
function showOffline(on) {
    els.offline.classList.toggle('is-hidden', !on);
    els.offline.classList.toggle('is-offline', on);
    if (on) {
        els.sub.textContent = 'geen verbinding';
    }
}

/**
 * Append any new transcript events and update the interim partial line, then
 * auto-scroll to the newest line.
 *
 * @param {Array<{ts:number,text:string}>} events - Final transcript events.
 * @param {string} partial - Current interim (word-by-word) text.
 * @returns {void}
 */
function renderTranscript(events, partial) {
    if (events.length > renderedEvents) {
        const frag = document.createDocumentFragment();
        for (let i = renderedEvents; i < events.length; i += 1) {
            const li = document.createElement('li');
            li.className = 'transcript__row';
            li.innerHTML =
                `<span class="transcript__time">#${i + 1}</span>` +
                `<span class="transcript__text">${escapeHtml(events[i].text || '')}</span>`;
            frag.appendChild(li);
        }
        els.transcript.appendChild(frag);
        renderedEvents = events.length;
    }
    els.partial.textContent = partial ? `… ${partial}` : '';
    els.transcriptCard.scrollTop = els.transcriptCard.scrollHeight;
}

/**
 * Apply a fresh state snapshot from the backend.
 *
 * Handles the offline sentinel from {@link startPolling}, switches button +
 * status text on phase changes, and (while active) renders the live transcript.
 * The ticking mm:ss timer is driven by the local 1s interval, not by polling.
 *
 * @param {object} st - State payload or `{ __offline: true }`.
 * @returns {void}
 */
function applyState(st) {
    if (st && st.__offline) {
        showOffline(true);
        return;
    }
    showOffline(false);

    const next = st.phase || 'idle';
    if (next !== phase) {
        phase = next;
        timerSeconds = 0;
        renderedEvents = 0;
        renderButton(phase);

        if (phase === 'ringing') {
            els.phase.textContent = 'alarmcentrale';
            els.status.textContent = 'Aan het bellen…';
            els.sub.textContent = 'wachten op de centrale';
            els.transcriptCard.classList.add('is-hidden');
            els.transcript.innerHTML = '';
            els.partial.textContent = '';
        } else if (phase === 'active') {
            els.phase.textContent = 'verbonden';
            els.status.textContent = '00:00';
            els.sub.textContent = 'u bent verbonden met de centrale';
            els.transcriptCard.classList.remove('is-hidden');
            els.transcript.innerHTML = '';
            els.partial.textContent = '';
        } else {
            els.phase.textContent = 'alarmcentrale';
            els.status.textContent = 'Beller';
            els.sub.textContent = '';
            els.transcriptCard.classList.add('is-hidden');
            els.transcript.innerHTML = '';
            els.partial.textContent = '';
        }
    }

    if (phase === 'active') {
        renderTranscript(st.events || [], st.partial || '');
    }
}

/**
 * Local 1-second tick: advances the connected-call timer in the status header.
 *
 * @returns {void}
 */
function tick() {
    if (phase === 'active') {
        timerSeconds += 1;
        els.status.textContent = mmss(timerSeconds);
    }
}

// --- Wire up -----------------------------------------------------------------
renderButton('idle');
els.callBtn.addEventListener('click', toggleCall);
setInterval(tick, 1000);
startPolling(applyState, POLL_MS);
