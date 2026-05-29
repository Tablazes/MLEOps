/**
 * VitaCall shared browser API client.
 *
 * Thin wrapper around the FastAPI backend (app/backend.py). Every call uses
 * `fetch` with JSON headers and a short AbortController timeout so the UI never
 * hangs when the backend is offline. Works whether the page is served by the
 * backend or opened standalone (file://) by reading an optional `?api=` query
 * param.
 *
 * @module api
 */

/**
 * Base URL of the VitaCall backend.
 *
 * Resolved from the `?api=` query string parameter when present (handy for
 * standalone/file:// usage or remote pairing), otherwise defaults to the local
 * dev server. No trailing slash.
 *
 * @type {string}
 */
export const API_BASE =
    new URLSearchParams(location.search).get('api') || 'http://127.0.0.1:8000';

/** Default per-request timeout in milliseconds. @type {number} */
const TIMEOUT_MS = 1500;

/**
 * Perform a fetch against the backend with JSON handling and a hard timeout.
 *
 * @param {string} path - Endpoint path beginning with `/` (e.g. `/call/state`).
 * @param {object} [options] - Request options.
 * @param {'GET'|'POST'} [options.method='GET'] - HTTP method.
 * @param {object|null} [options.body=null] - Plain object serialized as JSON.
 * @param {number} [options.timeoutMs=TIMEOUT_MS] - Abort after this many ms.
 * @returns {Promise<object>} Parsed JSON response body.
 * @throws {Error} On network failure, timeout, or non-2xx HTTP status.
 */
async function request(path, { method = 'GET', body = null, timeoutMs = TIMEOUT_MS } = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const init = {
            method,
            headers: { 'Accept': 'application/json' },
            signal: controller.signal,
        };
        if (body !== null) {
            init.headers['Content-Type'] = 'application/json';
            init.body = JSON.stringify(body);
        }
        const res = await fetch(`${API_BASE}${path}`, init);
        if (!res.ok) {
            throw new Error(`HTTP ${res.status} on ${path}`);
        }
        return await res.json();
    } finally {
        clearTimeout(timer);
    }
}

/**
 * Fetch the current call state.
 *
 * @returns {Promise<{phase:'idle'|'ringing'|'active',caller:string,started_at:number,events:Array<{ts:number,text:string}>,partial:string,call_id:number,active:boolean}>}
 * @throws {Error} When the backend is unreachable or returns an error.
 */
export async function getState() {
    return request('/call/state');
}

/**
 * Fetch recent call history (newest first, max 20).
 *
 * @returns {Promise<{calls:Array<{call_id:number,caller:string,started_at:number,ended_at:number,duration_s:number,events:Array<{ts:number,text:string}>}>}>}
 * @throws {Error} When the backend is unreachable or returns an error.
 */
export async function getHistory() {
    return request('/call/history');
}

/**
 * Start a new call (transitions phase idle -> ringing).
 *
 * @param {string} caller - Display name of the caller.
 * @returns {Promise<{ok:boolean,phase:'ringing',call_id:number}>}
 * @throws {Error} When the backend is unreachable or returns an error.
 */
export async function startCall(caller) {
    return request('/call/start', { method: 'POST', body: { caller } });
}

/**
 * Accept the ringing call (transitions phase ringing -> active).
 *
 * @returns {Promise<{ok:boolean,phase:'active'}>}
 * @throws {Error} When the backend is unreachable or returns an error.
 */
export async function acceptCall() {
    return request('/call/accept', { method: 'POST' });
}

/**
 * End the current call (transitions phase -> idle).
 *
 * @returns {Promise<{ok:boolean}>}
 * @throws {Error} When the backend is unreachable or returns an error.
 */
export async function endCall() {
    return request('/call/end', { method: 'POST' });
}

/**
 * Append a final transcript line (only valid while phase === 'active').
 *
 * @param {string} text - Finalized transcript line.
 * @returns {Promise<{ok:boolean}>}
 * @throws {Error} When the backend is unreachable or returns an error.
 */
export async function postTranscript(text) {
    return request('/call/transcript', { method: 'POST', body: { text } });
}

/**
 * Send an interim word-by-word partial (only valid while phase === 'active').
 *
 * @param {string} text - Current interim transcript text.
 * @returns {Promise<{ok:boolean}>}
 * @throws {Error} When the backend is unreachable or returns an error.
 */
export async function postPartial(text) {
    return request('/call/partial', { method: 'POST', body: { text } });
}

/**
 * Analyze text for sentiment and Dutch urgentie/medicatie keywords.
 *
 * @param {string} text - Text to analyze.
 * @returns {Promise<{sentiment:'positief'|'negatief',confidence:number,keywords:Array<{text:string,type:'urgentie'|'medicatie'}>}>}
 * @throws {Error} When the backend is unreachable or returns an error.
 */
export async function analyze(text) {
    return request('/analyze', { method: 'POST', body: { text } });
}

/**
 * Fetch service metrics (uptime, request counts, latency percentiles).
 *
 * @returns {Promise<{uptime_s:number,requests_total:number,requests_errors:number,error_rate:number,p50_ms:number,p95_ms:number,avg_confidence:number}>}
 * @throws {Error} When the backend is unreachable or returns an error.
 */
export async function getMetrics() {
    return request('/metrics');
}

/**
 * Fetch model drift indicators.
 *
 * @returns {Promise<{status:string,positive_rate:number,drift_score:number,samples:number}>}
 * @throws {Error} When the backend is unreachable or returns an error.
 */
export async function getDrift() {
    return request('/drift');
}

/**
 * Fetch backend health.
 *
 * @returns {Promise<{status:'healthy',model_loaded:boolean}>}
 * @throws {Error} When the backend is unreachable or returns an error.
 */
export async function getHealth() {
    return request('/health');
}

/**
 * Poll a fetcher on an interval. Invokes `fn` immediately, then every
 * `intervalMs`. Fetch errors are swallowed so polling never stops; on failure
 * `fn` is called with the sentinel `{ __offline: true }` so callers can render
 * an offline badge. The polled function's return value is passed to `fn`.
 *
 * @param {(data: object) => void} fn - Callback receiving fetched data, or
 *   `{ __offline: true }` when the request fails.
 * @param {number} intervalMs - Interval between polls in milliseconds.
 * @param {() => Promise<object>} [fetcher=getState] - Async function producing
 *   the data passed to `fn`.
 * @returns {() => void} Stop function that cancels the interval.
 */
export function startPolling(fn, intervalMs, fetcher = getState) {
    let stopped = false;

    async function tick() {
        let data;
        try {
            data = await fetcher();
        } catch {
            data = { __offline: true };
        }
        if (!stopped) {
            fn(data);
        }
    }

    tick();
    const id = setInterval(tick, intervalMs);

    return function stop() {
        stopped = true;
        clearInterval(id);
    };
}

/**
 * Escape a string for safe insertion into HTML (prevents injection when
 * rendering caller names / transcript text via innerHTML).
 *
 * @param {string} str - Raw string (coerced to string if not).
 * @returns {string} HTML-escaped string.
 */
export function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}
