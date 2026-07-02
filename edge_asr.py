"""VitaCall edge-ASR: Whisper-tiny finetunen op (synthetische) zorgdata.

Single source of truth voor het edge-model, zelfde patroon als serve.py:
het notebook importeert `EdgeASRTrainer`/`ZorgAudioBuilder` en toont alleen
gebruik + resultaten. Waarom Whisper i.p.v. Vosk: Vosk/Kaldi is praktisch
niet te finetunen; Whisper-tiny (39M) wel, en is na quantisatie (q5_0,
~31MB) klein genoeg voor een Raspberry Pi Zero 2 W met 512MB RAM.

Trainingsdata = mix van openbare Nederlandse spraak (Multilingual LibriSpeech,
zoals de opdracht "Common Voice of vergelijkbaar" vraagt) en synthetische
zorg-audio (gTTS) uit domein-templates. Echte gespreksaudio verlaat de
instelling nooit (privacy-eis). De 20 referentie-wavs in evidence/ref_audio/
zijn de held-out testset en komen nooit in de training terecht.
"""
import itertools
import json
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf

log = logging.getLogger("edge_asr")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SAMPLE_RATE = 16_000
BASE_MODEL = "openai/whisper-tiny"
FINETUNED_DIR = Path("models/whisper-tiny-vitacall-nl")
TRAIN_AUDIO_DIR = Path("evidence/zorg_train_audio")

# --------------------------------------------------------------------------- #
# Held-out testset: 20 vaste zorg-zinnen; de wavs staan in evidence/ref_audio/
# en zijn met synth() hieronder gegenereerd (gTTS -> ffmpeg 16kHz mono).
# --------------------------------------------------------------------------- #
HELDOUT_PAIRS = [
    ("evidence/ref_audio/ref_00.wav", "pijn op de borst"),
    ("evidence/ref_audio/ref_01.wav", "mijn moeder is gevallen"),
    ("evidence/ref_audio/ref_02.wav", "ik kan niet ademen"),
    ("evidence/ref_audio/ref_03.wav", "de patient heeft koorts"),
    ("evidence/ref_audio/ref_04.wav", "stuur een ambulance naar de hoofdstraat"),
    ("evidence/ref_audio/ref_05.wav", "bel onmiddellijk een dokter"),
    ("evidence/ref_audio/ref_06.wav", "de patient is bewusteloos geraakt"),
    ("evidence/ref_audio/ref_07.wav", "er is veel bloed bij de wond"),
    ("evidence/ref_audio/ref_08.wav", "hij heeft hevige pijn in zijn buik"),
    ("evidence/ref_audio/ref_09.wav", "mijn vader krijgt geen lucht meer"),
    ("evidence/ref_audio/ref_10.wav", "de ambulance is onderweg naar u"),
    ("evidence/ref_audio/ref_11.wav", "blijf rustig en haal diep adem"),
    ("evidence/ref_audio/ref_12.wav", "ik zie iemand op de grond liggen"),
    ("evidence/ref_audio/ref_13.wav", "haar hart klopt heel onregelmatig"),
    ("evidence/ref_audio/ref_14.wav", "geef de patient niets te eten of drinken"),
    ("evidence/ref_audio/ref_15.wav", "het slachtoffer reageert niet meer"),
    ("evidence/ref_audio/ref_16.wav", "er is brand op de tweede verdieping"),
    ("evidence/ref_audio/ref_17.wav", "kunt u uw adres herhalen alstublieft"),
    ("evidence/ref_audio/ref_18.wav", "de oude man is van de trap gevallen"),
    ("evidence/ref_audio/ref_19.wav", "zij heeft een allergische reactie"),
]

# --------------------------------------------------------------------------- #
# Zorg-trainingszinnen: templates x slots (disjunct van de held-out zinnen)
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# WER-harness: kopie van evidence/generate_ref_audio.py zodat de cijfers
# een-op-een vergelijkbaar zijn met de eerdere Vosk-metingen.
# --------------------------------------------------------------------------- #
ACCENT = "a-zàáâäçèéêëìíîïñòóôöùúûü0-9"


def _norm(t: str) -> list[str]:
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


def synth(text: str, wav_path: Path) -> None:
    """gTTS (nl) -> mp3 -> ffmpeg -> 16kHz mono 16-bit PCM WAV (als ref_audio)."""
    from gtts import gTTS
    with tempfile.TemporaryDirectory() as tmp:
        mp3 = os.path.join(tmp, "a.mp3")
        gTTS(text=text, lang="nl").save(mp3)
        subprocess.run(["ffmpeg", "-y", "-i", mp3, "-ar", str(SAMPLE_RATE), "-ac", "1",
                        "-sample_fmt", "s16", str(wav_path)], check=True, capture_output=True)


class ZorgAudioBuilder:
    """Bouwt de synthetische zorg-trainingsset: gTTS-basis + tempo-augmentatie.

    Cachet op bestandsnaam (skip-if-exists) zodat herhaald draaien goedkoop is.
    """

    def __init__(self, out_dir: Path = TRAIN_AUDIO_DIR):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def _augment(self, src: Path, dst: Path, tempo: float) -> None:
        # atempo verandert spreektempo zonder pitch-shift: goedkope augmentatie.
        subprocess.run(["ffmpeg", "-y", "-i", str(src), "-filter:a", f"atempo={tempo}",
                        "-ar", str(SAMPLE_RATE), "-ac", "1", "-sample_fmt", "s16",
                        str(dst)], check=True, capture_output=True)

    def build(self, sentences: list[str] | None = None) -> list[tuple[str, str]]:
        """Synthetiseer alle zinnen + 2 tempo-varianten; return (wav, tekst)-paren."""
        sentences = sentences or zorg_train_sentences()
        pairs: list[tuple[str, str]] = []
        for i, zin in enumerate(sentences):
            base = self.out_dir / f"zorg_{i:03d}.wav"
            if not base.exists():
                # gTTS breekt af bij te veel requests: retry met backoff.
                for poging, pauze in enumerate((5, 20, 60), start=1):
                    try:
                        synth(zin, base)
                        break
                    except Exception:
                        if poging == 3:
                            raise
                        log.warning("gTTS-fout bij clip %d, retry over %ds", i, pauze)
                        time.sleep(pauze)
                time.sleep(1.0)  # gTTS rate-limit ontzien
            pairs.append((str(base), zin))
            for tag, tempo in (("slow", 0.9), ("fast", 1.1)):
                aug = self.out_dir / f"zorg_{i:03d}_{tag}.wav"
                if not aug.exists():
                    self._augment(base, aug, tempo)
                pairs.append((str(aug), zin))
        log.info("Zorg-trainingsset: %d clips in %s", len(pairs), self.out_dir)
        return pairs


# --------------------------------------------------------------------------- #
# Openbare NL-spraak (streaming): Multilingual LibriSpeech, parquet en niet
# gated (Common Voice vereist een licentie-akkoord; MLS is "vergelijkbaar").
# --------------------------------------------------------------------------- #
EXTERN_BRON = "facebook/multilingual_librispeech"


def _decode_bytes(raw: bytes) -> np.ndarray | None:
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


# --------------------------------------------------------------------------- #
# Trainer
# --------------------------------------------------------------------------- #
class EdgeASRTrainer:
    """Lichte Whisper-tiny finetune binnen een tijdsbudget (MX350, 2GB VRAM).

    Geheugenstrategie: encoder bevroren, micro-batch 2 met gradient-accumulatie 8
    (effectieve batch 16), fp16 op GPU. Een timing-probe van enkele stappen
    bepaalt max_steps zodat de training binnen `minutes` blijft.
    """

    def __init__(self, model_name: str = BASE_MODEL, out_dir: Path = FINETUNED_DIR):
        self.model_name = model_name
        self.out_dir = Path(out_dir)

    def _device(self):
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"

    def _load_wav(self, path: str) -> np.ndarray:
        arr, rate = sf.read(path, dtype="float32")
        assert rate == SAMPLE_RATE, f"{path}: {rate}Hz, verwacht {SAMPLE_RATE}"
        return arr

    def build_dataset(self, zorg_pairs: list[tuple[str, str]],
                      extern_clips: list[tuple[np.ndarray, str]]):
        """Zet (audio, tekst)-paren om naar log-mel features + token-labels."""
        from datasets import Dataset
        from transformers import WhisperProcessor
        proc = WhisperProcessor.from_pretrained(self.model_name,
                                                language="Dutch", task="transcribe")
        feats, labels = [], []
        for arr, tekst in extern_clips + [(self._load_wav(p), t) for p, t in zorg_pairs]:
            feats.append(proc(arr, sampling_rate=SAMPLE_RATE).input_features[0])
            labels.append(proc.tokenizer(tekst).input_ids)
        ds = Dataset.from_dict({"input_features": feats, "labels": labels})
        log.info("Trainingsset: %d voorbeelden (%d openbaar + %d zorg)",
                 len(ds), len(extern_clips), len(zorg_pairs))
        return ds, proc

    def train(self, dataset, processor, minutes: int = 35) -> dict:
        """Finetune met tijdsbudget; bewaart het model in self.out_dir."""
        import torch
        from transformers import (Seq2SeqTrainer, Seq2SeqTrainingArguments,
                                  WhisperForConditionalGeneration)

        model = WhisperForConditionalGeneration.from_pretrained(self.model_name)
        for p in model.model.encoder.parameters():  # encoder bevriezen: minder VRAM
            p.requires_grad = False
        model.config.use_cache = False

        class Collator:
            def __call__(self, batch):
                # Expliciet float32: datasets bewaart lijsten als float64 en
                # dat botst met fp16-training (conv1d double vs half).
                feats = torch.tensor(np.array([b["input_features"] for b in batch],
                                              dtype=np.float32))
                lab = [torch.tensor(b["labels"]) for b in batch]
                labels = torch.nn.utils.rnn.pad_sequence(lab, batch_first=True,
                                                         padding_value=-100)
                return {"input_features": feats, "labels": labels}

        def args(steps: int, checkpoints: bool = False) -> Seq2SeqTrainingArguments:
            return Seq2SeqTrainingArguments(
                output_dir=str(self.out_dir / "_tmp"), max_steps=steps,
                per_device_train_batch_size=2, gradient_accumulation_steps=8,
                learning_rate=1e-5, warmup_steps=min(50, steps // 4),
                fp16=torch.cuda.is_available(), logging_steps=25,
                # Checkpoint elke 40 stappen: een onderbroken run kan hervatten.
                save_strategy="steps" if checkpoints else "no", save_steps=40,
                save_total_limit=1, report_to=[], remove_unused_columns=False,
                dataloader_num_workers=0, seed=42,
            )

        # Timing-probe: 4 stappen draaien en daaruit het stappenbudget afleiden.
        probe = Seq2SeqTrainer(model=model, args=args(4), train_dataset=dataset,
                               data_collator=Collator())
        t0 = time.perf_counter()
        probe.train()
        sec_per_step = (time.perf_counter() - t0) / 4
        max_steps = int(max(60, min(600, minutes * 60 / sec_per_step)))
        log.info("Probe: %.1fs/stap -> max_steps=%d (budget %d min)",
                 sec_per_step, max_steps, minutes)

        trainer = Seq2SeqTrainer(model=model, args=args(max_steps, checkpoints=True),
                                 train_dataset=dataset, data_collator=Collator())
        heeft_checkpoint = any((self.out_dir / "_tmp").glob("checkpoint-*"))
        result = trainer.train(resume_from_checkpoint=heeft_checkpoint or None)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        model.config.use_cache = True
        model.save_pretrained(self.out_dir)
        processor.save_pretrained(self.out_dir)
        info = {"max_steps": max_steps, "sec_per_step": round(sec_per_step, 2),
                "train_loss": round(result.training_loss, 4),
                "train_runtime_s": round(result.metrics["train_runtime"], 1),
                "device": self._device()}
        log.info("Klaar: %s", info)
        return info

    def evaluate(self, model_source: str | Path,
                 pairs: list[tuple[str, str]] = HELDOUT_PAIRS) -> dict:
        """Meet WER + RTF op de held-out zorgtestset voor een gegeven model."""
        import torch
        from transformers import WhisperForConditionalGeneration, WhisperProcessor
        device = self._device()
        proc = WhisperProcessor.from_pretrained(model_source)
        model = WhisperForConditionalGeneration.from_pretrained(model_source).to(device).eval()
        rows, wers, rtfs = [], [], []
        for path, ref in pairs:
            arr = self._load_wav(path)
            feats = proc(arr, sampling_rate=SAMPLE_RATE,
                         return_tensors="pt").input_features.to(device)
            t0 = time.perf_counter()
            with torch.no_grad():
                ids = model.generate(feats, language="nl", task="transcribe",
                                     max_new_tokens=64)
            dec = time.perf_counter() - t0
            hyp = proc.batch_decode(ids, skip_special_tokens=True)[0].strip()
            w, rtf = wer(ref, hyp), dec / (len(arr) / SAMPLE_RATE)
            wers.append(w)
            rtfs.append(rtf)
            rows.append({"wav": Path(path).name, "ref": ref, "hyp": hyp,
                         "wer": round(w, 3), "rtf": round(rtf, 3)})
        return {"model": str(model_source), "rows": rows,
                "mean_wer": round(float(np.mean(wers)), 4),
                "mean_rtf": round(float(np.mean(rtfs)), 3)}


def run_finetune(minutes: int = 35, extern_n: int = 300) -> dict:
    """Volledige finetune-run incl. MLflow-tracking; return alle kerncijfers.

    Mix van openbare NL-spraak (MLS, conform opdracht "Common Voice of
    vergelijkbaar") en synthetische zorg-audio; testset blijft held-out.
    """
    import mlflow
    trainer = EdgeASRTrainer()
    zorg_pairs = ZorgAudioBuilder().build()
    extern_clips = load_nl_clips(extern_n)
    dataset, proc = trainer.build_dataset(zorg_pairs, extern_clips)

    mlflow.set_experiment("edge-asr-finetune")
    with mlflow.start_run(run_name="whisper-tiny-zorgdata"):
        before = trainer.evaluate(BASE_MODEL)
        info = trainer.train(dataset, proc, minutes=minutes)
        after = trainer.evaluate(trainer.out_dir)
        mlflow.log_params({"base_model": BASE_MODEL, "extern_bron": EXTERN_BRON,
                           "n_train": len(dataset), "n_zorg": len(zorg_pairs),
                           "n_extern": len(extern_clips),
                           **{k: info[k] for k in
                              ("max_steps", "sec_per_step", "device")}})
        mlflow.log_metrics({"wer_zorg_before": before["mean_wer"],
                            "wer_zorg_after": after["mean_wer"],
                            "train_loss": info["train_loss"],
                            "train_runtime_s": info["train_runtime_s"]})
        mlflow.log_dict({"before": before, "after": after}, "wer_evaluatie.json")
    resultaat = {"before": before, "after": after, "train": info}
    log.info("WER zorg-testset: %.4f -> %.4f", before["mean_wer"], after["mean_wer"])
    return resultaat


if __name__ == "__main__":
    uitkomst = run_finetune()
    Path("evidence").mkdir(exist_ok=True)
    with open("evidence/2026-07-02_whisper-finetune-run.json", "w", encoding="utf-8") as f:
        json.dump(uitkomst, f, ensure_ascii=False, indent=2)
    print(json.dumps({"wer_before": uitkomst["before"]["mean_wer"],
                      "wer_after": uitkomst["after"]["mean_wer"]}, indent=2))
