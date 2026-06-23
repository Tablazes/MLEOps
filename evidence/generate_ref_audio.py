"""Genereer extra NL referentie-audio (gTTS -> ffmpeg 16k mono PCM) en meet WER.
Self-contained: hergebruikt dezelfde harness-logica als notebook cel 44.
"""
import os, re, json, time, wave, subprocess, tempfile
from pathlib import Path

OUT = Path('evidence/ref_audio')
OUT.mkdir(parents=True, exist_ok=True)
VOSK_DIR = Path('models') / 'vosk-nl'

# 15 nieuwe nood-/zorg-zinnen (varierende lengte, met accenten voor normalize-test).
NEW = [
    'bel onmiddellijk een dokter',
    'de patient is bewusteloos geraakt',
    'er is veel bloed bij de wond',
    'hij heeft hevige pijn in zijn buik',
    'mijn vader krijgt geen lucht meer',
    'de ambulance is onderweg naar u',
    'blijf rustig en haal diep adem',
    'ik zie iemand op de grond liggen',
    'haar hart klopt heel onregelmatig',
    'geef de patient niets te eten of drinken',
    'het slachtoffer reageert niet meer',
    'er is brand op de tweede verdieping',
    'kunt u uw adres herhalen alstublieft',
    'de oude man is van de trap gevallen',
    'zij heeft een allergische reactie',
]


def synth(text, wav_path):
    """gTTS (nl) -> mp3 -> ffmpeg -> 16kHz mono 16-bit PCM WAV."""
    from gtts import gTTS
    with tempfile.TemporaryDirectory() as tmp:
        mp3 = os.path.join(tmp, 'a.mp3')
        gTTS(text=text, lang='nl').save(mp3)
        subprocess.run(
            ['ffmpeg', '-y', '-i', mp3, '-ar', '16000', '-ac', '1',
             '-sample_fmt', 's16', str(wav_path)],
            check=True, capture_output=True)


# Genereer ref_05..ref_19 (skip als al aanwezig).
for idx, text in enumerate(NEW, start=5):
    wav = OUT / f'ref_{idx:02d}.wav'
    if wav.exists():
        print(f'skip (bestaat): {wav.name}')
        continue
    synth(text, wav)
    w = wave.open(str(wav), 'rb')
    print(f'made {wav.name}: {w.getframerate()}Hz {w.getnchannels()}ch '
          f'{round(w.getnframes()/w.getframerate(),2)}s  "{text}"')
    w.close()

print('\n=== Genereren klaar; standalone WER-meting op alle 20 ===')

# --- harness (kopie van notebook-logica, met GEFIXTE accent-regex) ---
ACCENT = 'a-zàáâäçèéêëìíîïñòóôöùúûü0-9'


def _norm(t):
    return re.findall(f'[{ACCENT}]+', t.lower())


def wer(ref, hyp):
    r, h = _norm(ref), _norm(hyp)
    if not r:
        return 0.0 if not h else 1.0
    dp = [[0]*(len(h)+1) for _ in range(len(r)+1)]
    for i in range(len(r)+1):
        dp[i][0] = i
    for j in range(len(h)+1):
        dp[0][j] = j
    for i in range(1, len(r)+1):
        for j in range(1, len(h)+1):
            c = 0 if r[i-1] == h[j-1] else 1
            dp[i][j] = min(dp[i-1][j]+1, dp[i][j-1]+1, dp[i-1][j-1]+c)
    return dp[len(r)][len(h)] / len(r)


from vosk import Model, KaldiRecognizer, SetLogLevel
SetLogLevel(-1)
model = Model(str(VOSK_DIR))

PAIRS = [
    ('evidence/ref_audio/ref_00.wav', 'pijn op de borst'),
    ('evidence/ref_audio/ref_01.wav', 'mijn moeder is gevallen'),
    ('evidence/ref_audio/ref_02.wav', 'ik kan niet ademen'),
    ('evidence/ref_audio/ref_03.wav', 'de patient heeft koorts'),
    ('evidence/ref_audio/ref_04.wav', 'stuur een ambulance naar de hoofdstraat'),
] + [(f'evidence/ref_audio/ref_{i:02d}.wav', t) for i, t in enumerate(NEW, start=5)]


def transcribe(path):
    wf = wave.open(path, 'rb')
    rate = wf.getframerate()
    dur = wf.getnframes()/float(rate)
    rec = KaldiRecognizer(model, rate)
    rec.SetWords(False)
    t0 = time.perf_counter()
    parts = []
    while True:
        d = wf.readframes(4000)
        if not d:
            break
        if rec.AcceptWaveform(bytes(d)):
            parts.append(json.loads(rec.Result()).get('text', ''))
    parts.append(json.loads(rec.FinalResult()).get('text', ''))
    dec = time.perf_counter()-t0
    wf.close()
    return ' '.join(p for p in parts if p).strip(), dur, dec


rows, wers, rtfs = [], [], []
for path, ref in PAIRS:
    hyp, dur, dec = transcribe(path)
    w = wer(ref, hyp)
    rtf = dec/dur if dur else 0
    wers.append(w); rtfs.append(rtf)
    rows.append((Path(path).name, ref, hyp, round(w, 3), round(rtf, 3)))

print(f'\n{"wav":<12}{"WER":>6}{"RTF":>7}  ref -> hyp')
for name, ref, hyp, w, rtf in rows:
    print(f'{name:<12}{w:>6}{rtf:>7}  "{ref}" -> "{hyp}"')
print(f'\nN={len(PAIRS)}  mean WER={round(sum(wers)/len(wers),4)}  '
      f'mean RTF={round(sum(rtfs)/len(rtfs),3)}')
