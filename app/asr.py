"""Edge-ASR: Nederlandse spraak-naar-tekst met Vosk-NL.

Dit is het *edge*-model van VitaCall: het draait lokaal op de machine van de
medewerker en zet binnenkomende audio om naar tekst. De ruwe audio verlaat de
instelling nooit; alleen de (geanonimiseerde) tekst gaat naar de cloud voor
sentiment- en urgentie-analyse. ASR op de edge is daarmee de privacy-oplossing
zelf, niet een verkleind cloud-model.

Het model is een kant-en-klaar Kaldi/Vosk-model (`models/vosk-nl/`), geen door
ons getrainde classifier. Wij evalueren het hier: word error rate (WER),
modelgrootte en real-time-factor (RTF). De live mic-variant zit in
`app/signals.py` (AudioBridge); dit bestand bevat de *bestands*-decoder + de
evaluatie-helpers zodat het notebook reproduceerbaar kan meten.
"""
from __future__ import annotations

import json
import re
import time
import wave
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VOSK_DIR = ROOT / "models" / "vosk-nl"


def _normalize(text: str) -> list[str]:
    """Lowercase, strip leestekens -> woordenlijst. Voor eerlijke WER-meting."""
    return re.findall(r"[a-zàáâäçèéêëìíîïñòóôöùúûü0-9]+", text.lower())


def word_error_rate(reference: str, hypothesis: str) -> float:
    """WER = (substituties + inserties + deleties) / #referentiewoorden.

    Standaard ASR-metric. Levenshtein-afstand op woordniveau, genormaliseerd
    door de lengte van de referentie. Geen externe dependency (geen jiwer).
    """
    ref, hyp = _normalize(reference), _normalize(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    # Klassieke DP-matrix (edit distance op woorden).
    dp = [[0] * (len(hyp) + 1) for _ in range(len(ref) + 1)]
    for i in range(len(ref) + 1):
        dp[i][0] = i
    for j in range(len(hyp) + 1):
        dp[0][j] = j
    for i in range(1, len(ref) + 1):
        for j in range(1, len(hyp) + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1,        # deletie
                           dp[i][j - 1] + 1,        # insertie
                           dp[i - 1][j - 1] + cost)  # substitutie/match
    return dp[len(ref)][len(hyp)] / len(ref)


@dataclass
class ASRResult:
    """Uitkomst van een bestands-transcriptie + meetgegevens."""

    text: str
    audio_seconds: float
    decode_seconds: float

    @property
    def rtf(self) -> float:
        """Real-time-factor: decode-tijd / audio-duur. <1.0 = sneller dan real-time."""
        return self.decode_seconds / self.audio_seconds if self.audio_seconds else 0.0


class EdgeASR:
    """Vosk-NL bestands-decoder. Laadt het model eenmalig, transcribeert WAV's."""

    def __init__(self, model_dir: Path | str = VOSK_DIR) -> None:
        self.model_dir = Path(model_dir)
        self._model = None

    @property
    def available(self) -> bool:
        """True als Vosk geïnstalleerd is en het model op schijf staat."""
        try:
            import vosk  # noqa: F401
        except ImportError:
            return False
        return self.model_dir.is_dir()

    def model_size_mb(self) -> float:
        """Totale modelgrootte op schijf (MB), edge-footprint."""
        total = sum(p.stat().st_size for p in self.model_dir.rglob("*") if p.is_file())
        return round(total / (1024 * 1024), 1)

    def _load(self) -> None:
        if self._model is not None:
            return
        from vosk import Model, SetLogLevel
        SetLogLevel(-1)  # onderdruk Kaldi-ruis
        self._model = Model(str(self.model_dir))

    def transcribe_wav(self, wav_path: Path | str) -> ASRResult:
        """Transcribeer een mono 16-bit WAV. Meet decode-tijd en audio-duur.

        Vosk verwacht 16-bit PCM mono. Andere sample-rates werken; we lezen de
        rate uit de WAV-header zodat de recognizer correct is geconfigureerd.
        """
        from vosk import KaldiRecognizer
        self._load()
        wf = wave.open(str(wav_path), "rb")
        rate = wf.getframerate()
        audio_seconds = wf.getnframes() / float(rate)
        rec = KaldiRecognizer(self._model, rate)
        rec.SetWords(False)
        t0 = time.perf_counter()
        parts: list[str] = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(bytes(data)):
                parts.append(json.loads(rec.Result()).get("text", ""))
        parts.append(json.loads(rec.FinalResult()).get("text", ""))
        decode_seconds = time.perf_counter() - t0
        wf.close()
        text = " ".join(p for p in parts if p).strip()
        return ASRResult(text=text, audio_seconds=audio_seconds,
                         decode_seconds=round(decode_seconds, 3))


def evaluate(pairs: list[tuple[Path | str, str]],
             model_dir: Path | str = VOSK_DIR) -> dict:
    """Evalueer de edge-ASR op (wav-pad, referentietekst)-paren.

    Geeft per sample de WER + de gemiddelde WER, gemiddelde RTF en modelgrootte.
    Als Vosk/het model ontbreekt of er geen paren zijn, rapporteren we dat
    eerlijk in plaats van een getal te verzinnen.
    """
    asr = EdgeASR(model_dir)
    if not asr.available:
        return {"status": "vosk_of_model_ontbreekt", "samples": 0}
    if not pairs:
        return {"status": "geen_referentie_audio", "samples": 0,
                "model_size_mb": asr.model_size_mb()}
    per_sample = []
    for wav_path, reference in pairs:
        res = asr.transcribe_wav(wav_path)
        per_sample.append({
            "wav": str(wav_path),
            "reference": reference,
            "hypothesis": res.text,
            "wer": round(word_error_rate(reference, res.text), 4),
            "rtf": round(res.rtf, 3),
        })
    n = len(per_sample)
    return {
        "status": "ok",
        "samples": n,
        "model_size_mb": asr.model_size_mb(),
        "mean_wer": round(sum(s["wer"] for s in per_sample) / n, 4),
        "mean_rtf": round(sum(s["rtf"] for s in per_sample) / n, 3),
        "per_sample": per_sample,
    }
