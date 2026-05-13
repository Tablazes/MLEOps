"""FileBus (file-based JSON signaling) + AudioBridge (sounddevice loopback + vosk STT)."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal


class FileBus(QObject):
    """Polling JSON bus tussen operator & caller op dezelfde host."""

    message = Signal(dict)

    def __init__(self, role: str, signal_file: Path) -> None:
        super().__init__()
        self.role = role
        self._file = signal_file
        self._last_seen = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(150)

    def _read(self) -> dict:
        if not self._file.exists():
            return {"seq": 0, "messages": []}
        try:
            with open(self._file, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {"seq": 0, "messages": []}

    def _write(self, data: dict) -> None:
        tmp = self._file.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        tmp.replace(self._file)

    def send(self, msg: dict) -> None:
        data = self._read()
        data["seq"] = int(data.get("seq", 0)) + 1
        data.setdefault("messages", []).append({"id": data["seq"], "from": self.role, "ts": time.time(), **msg})
        data["messages"] = data["messages"][-200:]
        self._write(data)

    def _poll(self) -> None:
        for m in self._read().get("messages", []):
            if m["id"] <= self._last_seen:
                continue
            self._last_seen = m["id"]
            if m.get("from") != self.role:
                self.message.emit(m)

    def reset(self) -> None:
        try:
            self._file.unlink(missing_ok=True)
        except OSError:
            pass


class AudioBridge(QObject):
    """Mic loopback + optionele vosk STT met partial-results (woord-voor-woord)."""

    transcript = Signal(str)         # final, complete utterance
    partial = Signal(str)            # interim, still-being-spoken

    def __init__(self, vosk_model_dir: Path) -> None:
        super().__init__()
        self._vosk_dir = vosk_model_dir
        self._stream = None
        self._stt_thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> bool:
        try:
            import numpy as np  # noqa: F401
            import sounddevice as sd  # type: ignore[import-not-found]
        except ImportError:
            return False
        try:
            self._stream = sd.Stream(
                samplerate=16000, channels=1, dtype="int16",
                callback=lambda indata, outdata, frames, t, s: outdata.__setitem__(slice(None), indata),
            )
            self._stream.start()
        except Exception:
            self._stream = None
            return False
        self._start_stt()
        return True

    def _start_stt(self) -> None:
        try:
            from vosk import KaldiRecognizer, Model  # type: ignore
        except ImportError:
            return
        if not self._vosk_dir.exists():
            return

        def _run() -> None:
            try:
                import json as _json
                import sounddevice as sd  # type: ignore[import-not-found]
                model = Model(str(self._vosk_dir))
                rec = KaldiRecognizer(model, 16000)
                # Kleinere blocksize = sneller partial-update (~150ms i.p.v. 250ms).
                with sd.RawInputStream(samplerate=16000, blocksize=2400, dtype="int16", channels=1) as inp:
                    last_partial = ""
                    while not self._stop.is_set():
                        data, _ = inp.read(2400)
                        if rec.AcceptWaveform(bytes(data)):
                            text = _json.loads(rec.Result()).get("text", "").strip()
                            last_partial = ""
                            if text:
                                self.transcript.emit(text)
                        else:
                            partial = _json.loads(rec.PartialResult()).get("partial", "").strip()
                            if partial and partial != last_partial:
                                last_partial = partial
                                self.partial.emit(partial)
            except Exception:
                return

        self._stt_thread = threading.Thread(target=_run, daemon=True)
        self._stt_thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
