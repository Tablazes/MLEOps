"""Edge-ASR audio-plumbing: single source of truth.

De losse audio-helpers rond de Whisper-finetune -- WER-metriek, gTTS-synthese,
ffmpeg-conversie/tempo-augmentatie, wav-load en het streamen van openbare
NL-spraak -- staan hier, zodat het notebook (sectie 2) de OOP-showcase overhoudt:
de EdgeASRTrainer- en ZorgAudioBuilder-klassen importeren deze functies i.p.v.
ze te dupliceren. Ook de deterministische slot-filling voor de zorg-trainingszinnen
zit hier.
"""
import itertools
import logging
import os
import subprocess
import tempfile

import numpy as np
import soundfile as sf

log = logging.getLogger("vitacall")

SAMPLE_RATE = 16_000
# Openbare NL-spraak (streaming): Multilingual LibriSpeech (Common Voice vereist licentie-akkoord).
EXTERN_BRON = "facebook/multilingual_librispeech"

# WER normaliseert op deze tekens (accenten + cijfers meegenomen).
ACCENT = "a-zàáâäçèéêëìíîïñòóôöùúûü0-9"


def _norm(t: str) -> list[str]:
    """Split tekst in genormaliseerde woorden voor de WER-vergelijking."""
    import re
    return re.findall(f"[{ACCENT}]+", t.lower())


def wer(ref: str, hyp: str) -> float:
    """Word error rate via Levenshtein-afstand op genormaliseerde woorden."""
    r, h = _norm(ref), _norm(hyp)
    if not r:
        return 0.0 if not h else 1.0
    dp = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        dp[i][0] = i
    for j in range(len(h) + 1):
        dp[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            c = 0 if r[i - 1] == h[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + c)
    return dp[len(r)][len(h)] / len(r)


def synth(text: str, wav_path) -> None:
    """gTTS (nl) -> mp3 -> ffmpeg -> 16kHz mono 16-bit PCM WAV (als ref_audio)."""
    from gtts import gTTS
    with tempfile.TemporaryDirectory() as tmp:
        mp3 = os.path.join(tmp, "a.mp3")
        gTTS(text=text, lang="nl").save(mp3)
        subprocess.run(["ffmpeg", "-y", "-i", mp3, "-ar", str(SAMPLE_RATE), "-ac", "1",
                        "-sample_fmt", "s16", str(wav_path)], check=True, capture_output=True)


def augment_tempo(src, dst, tempo: float) -> None:
    """atempo verandert spreektempo zonder pitch-shift: goedkope augmentatie."""
    subprocess.run(["ffmpeg", "-y", "-i", str(src), "-filter:a", f"atempo={tempo}",
                    "-ar", str(SAMPLE_RATE), "-ac", "1", "-sample_fmt", "s16",
                    str(dst)], check=True, capture_output=True)


def load_wav(path: str) -> np.ndarray:
    """Lees een WAV als float32 en controleer de sample-rate."""
    arr, rate = sf.read(path, dtype="float32")
    assert rate == SAMPLE_RATE, f"{path}: {rate}Hz, verwacht {SAMPLE_RATE}"
    return arr


def _decode_bytes(raw: bytes):
    """Decodeer audio-bytes (mp3/flac/wav) naar 16kHz mono float32 via ffmpeg."""
    p = subprocess.run(["ffmpeg", "-i", "pipe:0", "-f", "s16le", "-ar", str(SAMPLE_RATE),
                        "-ac", "1", "pipe:1"], input=raw, capture_output=True)
    if p.returncode != 0 or not p.stdout:
        return None
    return np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def load_nl_clips(n: int = 300) -> list[tuple[np.ndarray, str]]:
    """Streamt n bruikbare Nederlandse spraakclips (3-30 woorden, <=30s)."""
    from datasets import Audio, load_dataset
    ds = load_dataset(EXTERN_BRON, "dutch", split="9_hours", streaming=True)
    ds = ds.cast_column("audio", Audio(decode=False))
    clips: list[tuple[np.ndarray, str]] = []
    for ex in ds:
        tekst = (ex.get("transcript") or "").strip().lower()
        if not 3 <= len(tekst.split()) <= 30:
            continue
        arr = _decode_bytes(ex["audio"]["bytes"])
        if arr is None or not SAMPLE_RATE <= len(arr) <= 30 * SAMPLE_RATE:
            continue
        clips.append((arr, tekst))
        if len(clips) >= n:
            break
    log.info("Openbare NL-spraak: %d clips uit %s", len(clips), EXTERN_BRON)
    return clips


# Zorg-trainingszinnen via slot-filling: disjunct van de held-out testzinnen.
_SYMPTOMEN = ["hoofdpijn", "duizeligheid", "misselijkheid", "rugpijn", "kortademigheid",
              "hoge koorts", "hartkloppingen", "een verstuikte enkel", "uitdroging"]
_MEDICATIE = ["paracetamol", "ibuprofen", "insuline", "antibiotica",
              "bloedverdunners", "de inhalator", "een epipen"]
_PERSONEN = ["de bewoner", "mevrouw de vries", "meneer jansen", "de client op kamer acht"]
_TEMPLATES = [
    "{p} heeft last van {s}",
    "{p} klaagt al de hele dag over {s}",
    "wij maken ons zorgen omdat {p} {s} heeft",
    "kunt u {m} klaarleggen voor {p}",
    "{p} is vergeten om {m} in te nemen",
    "de huisarts heeft {m} voorgeschreven tegen {s}",
    "graag een terugbelverzoek over {m} voor {p}",
    "na de val heeft {p} nu ook {s}",
]


def zorg_train_sentences(limit: int = 120) -> list[str]:
    """Genereer domein-trainingszinnen via slot-filling (deterministische volgorde)."""
    combos = itertools.product(_TEMPLATES, _PERSONEN, _SYMPTOMEN, _MEDICATIE)
    out: list[str] = []
    for tpl, p, s, m in combos:
        zin = tpl.format(p=p, s=s, m=m)
        if zin not in out:
            out.append(zin)
        if len(out) >= limit:
            break
    return out
