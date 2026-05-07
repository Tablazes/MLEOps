"""VitaCall desktop UI — pure Python via PySide6.

Drop-in replacement for de hele electron/ folder. Geen npm, geen JavaScript.

Routes:
    python ui.py              # operator (alarmcentrale) view
    python ui.py --mobile     # caller (mobile) view

Audio + STT:
    Microfoon → operator-output via sounddevice loopback wanneer beide views
    op dezelfde machine draaien. STT via vosk indien geinstalleerd, anders
    valt het terug op een tekst-input fallback (typ wat de beller "zegt").

Signaling:
    Tussen 2 vensters op dezelfde host gebruiken we een file-based bus
    (signaling.json). Genoeg voor demo. Voor multi-machine demo: vervang
    FileBus door een websocket-implementatie.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import requests
from PySide6.QtCore import (
    QObject,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

API_URL = "http://127.0.0.1:8000"
ROOT = Path(__file__).resolve().parent.parent  # repo root (one above app/)
LITE_MODEL_PATH = ROOT / "models" / "sentiment_lite.json"
SIGNAL_FILE = ROOT / "signaling.json"

URGENT = ["pijn", "borst", "benauwd", "bewusteloos", "bloed", "hartaanval",
          "koorts", "flauwgevallen", "gevallen", "niet ademen", "overdosis"]
MEDS = ["paracetamol", "ibuprofen", "insuline", "antibiotica", "medicatie",
        "bloedverdunner", "inhalator", "epipen"]


def find_keywords(text: str) -> list[dict]:
    t = text.lower()
    out = [{"text": k, "type": "urgentie"} for k in URGENT if k in t]
    out += [{"text": k, "type": "medicatie"} for k in MEDS if k in t]
    return out


@dataclass
class EdgeModel:
    vocab: dict[str, int]
    idf: list[float]
    coef: list[float]
    bias: float

    @classmethod
    def load(cls, path: Path) -> "EdgeModel | None":
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return cls(d["vocab"], d["idf"], d["coef"], float(d["bias"]))

    def score(self, text: str) -> dict | None:
        tokens = re.findall(r"[a-zàáâäçèéêëìíîïñòóôöùúûü']+", text.lower())
        if not tokens:
            return None
        tf: dict[str, int] = {}
        for tok in tokens:
            tf[tok] = tf.get(tok, 0) + 1
        s = self.bias
        n = len(tokens)
        for tok, count in tf.items():
            i = self.vocab.get(tok)
            if i is not None:
                s += (count / n) * self.idf[i] * self.coef[i]
        p = 1 / (1 + math.exp(-s))
        return {
            "sentiment": "positief" if p > 0.5 else "negatief",
            "confidence": round(max(p, 1 - p), 3),
        }


def score_text(text: str, edge: EdgeModel | None) -> dict | None:
    """Cloud-eerst scoring met edge-fallback."""
    try:
        r = requests.post(f"{API_URL}/analyze", json={"text": text}, timeout=1.5)
        if r.ok:
            d = r.json()
            d["source"] = "cloud"
            return d
    except requests.RequestException:
        pass
    if edge is None:
        return None
    res = edge.score(text)
    if res is None:
        return None
    res["keywords"] = find_keywords(text)
    res["source"] = "edge"
    return res


def api_health() -> bool:
    try:
        r = requests.get(f"{API_URL}/health", timeout=0.7)
        return r.ok
    except requests.RequestException:
        return False


# ====== Signaling (file-based bus tussen operator & caller op zelfde host) ======
class FileBus(QObject):
    """Polling-based JSON bus. Houdt het simpel; geen externe broker nodig.

    Layout van signaling.json:
        {"seq": <int>, "messages": [{"id": int, "from": "caller|operator", ...}, ...]}
    """

    message = Signal(dict)

    def __init__(self, role: str) -> None:
        super().__init__()
        self.role = role
        self._last_seen = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(150)

    def _read(self) -> dict:
        if not SIGNAL_FILE.exists():
            return {"seq": 0, "messages": []}
        try:
            with open(SIGNAL_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {"seq": 0, "messages": []}

    def _write(self, data: dict) -> None:
        tmp = SIGNAL_FILE.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        tmp.replace(SIGNAL_FILE)

    def send(self, msg: dict) -> None:
        data = self._read()
        data["seq"] = int(data.get("seq", 0)) + 1
        msg_with_meta = {"id": data["seq"], "from": self.role, "ts": time.time(), **msg}
        data.setdefault("messages", []).append(msg_with_meta)
        data["messages"] = data["messages"][-200:]
        self._write(data)

    def _poll(self) -> None:
        data = self._read()
        for m in data.get("messages", []):
            if m["id"] <= self._last_seen:
                continue
            self._last_seen = m["id"]
            if m.get("from") != self.role:
                self.message.emit(m)

    def reset(self) -> None:
        try:
            SIGNAL_FILE.unlink(missing_ok=True)
        except OSError:
            pass


# ====== Audio + STT (best-effort, valt terug op tekst-input bij ontbreken) ======
class AudioBridge(QObject):
    """Mic → speakers loopback. Veilige fallback wanneer sounddevice ontbreekt."""

    transcript = Signal(str)

    def __init__(self) -> None:
        super().__init__()
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
                samplerate=16000,
                channels=1,
                dtype="int16",
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
        model_dir = ROOT / "models" / "vosk-nl"
        if not model_dir.exists():
            return

        def _run() -> None:
            try:
                import sounddevice as sd  # type: ignore[import-not-found]
                model = Model(str(model_dir))
                rec = KaldiRecognizer(model, 16000)
                with sd.RawInputStream(samplerate=16000, blocksize=4000,
                                       dtype="int16", channels=1) as inp:
                    while not self._stop.is_set():
                        data, _ = inp.read(4000)
                        if rec.AcceptWaveform(bytes(data)):
                            text = json.loads(rec.Result()).get("text", "").strip()
                            if text:
                                self.transcript.emit(text)
            except Exception:
                return

        self._stt_thread = threading.Thread(target=_run, daemon=True)
        self._stt_thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._stream is not None:
            try:
                self._stream.stop(); self._stream.close()
            except Exception:
                pass
            self._stream = None


# ====== Style (iPhone-call-stijl, zwart/grijze panels) ======
STYLE = """
* { font-family: 'Segoe UI', 'Inter', sans-serif; color: #fff; }
QWidget#shell  { background: #111113; }
QWidget#admin  { background: #111113; border-right: 1px solid rgba(255,255,255,0.07); }
QWidget#call   { background: #111113; }
QWidget#mobile { background: #111113; }
QLabel#brand   { font-size: 14px; font-weight: 700; color: #fff; }
QLabel#caller_name { font-size: 42px; font-weight: 600; letter-spacing: -0.5px; }
QLabel#caller_sub  { color: rgba(255,255,255,0.5); font-size: 15px; }
QLabel#section_title {
    font-size: 10px; font-weight: 700; letter-spacing: 1.2px;
    color: rgba(255,255,255,0.45); text-transform: uppercase;
}
QLabel.dim   { color: rgba(255,255,255,0.3); font-style: italic; font-size: 12px; }
QLabel.empty { color: rgba(255,255,255,0.3); font-style: italic; font-size: 12px; }
QLabel.pos   { color: #34c759; font-weight: 700; }
QLabel.neg   { color: #ff3b30; font-weight: 700; }
QLabel.amb   { color: #ff9f0a; font-weight: 700; }
QLabel.metric_label { font-size: 9px; color: rgba(255,255,255,0.45); letter-spacing: 0.5px; font-weight: 600; }
QFrame.metric_box {
    background: #1c1c1e;
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 8px;
}
QLabel#pill_on  { background: rgba(52,199,89,0.15); color: #34c759;
                   font-size: 10px; padding: 2px 8px; border-radius: 8px; font-weight: 700; }
QLabel#pill_off { background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.45);
                   font-size: 10px; padding: 2px 8px; border-radius: 8px; font-weight: 700; }
QFrame#row_pos { background: rgba(52,199,89,0.07); border-left: 3px solid #34c759; border-radius: 10px; }
QFrame#row_neg { background: rgba(255,59,48,0.07); border-left: 3px solid #ff3b30; border-radius: 10px; }
QFrame#row     { background: #1c1c1e; border-left: 3px solid rgba(255,255,255,0.2); border-radius: 10px; }
QPushButton#accept {
    background: #34c759; border-radius: 36px; min-width: 72px; min-height: 72px;
    max-width: 72px; max-height: 72px; font-weight: 700;
}
QPushButton#decline, QPushButton#endcall {
    background: #ff3b30; border-radius: 36px; min-width: 72px; min-height: 72px;
    max-width: 72px; max-height: 72px; font-weight: 700;
}
QPushButton#mob_call {
    background: #34c759; border-radius: 40px; min-width: 80px; min-height: 80px;
    max-width: 80px; max-height: 80px; font-size: 28px; font-weight: 700;
}
QPushButton#mob_end {
    background: #ff3b30; border-radius: 40px; min-width: 80px; min-height: 80px;
    max-width: 80px; max-height: 80px; font-size: 24px; font-weight: 700;
}
QLineEdit { background: #1c1c1e; padding: 8px 12px; border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.07); font-size: 13px; }
QScrollArea, QListWidget { background: transparent; border: 0; }
QListWidget::item { padding: 8px 10px; border-radius: 6px; font-size: 13px; }
QListWidget::item:hover { background: rgba(255,255,255,0.04); }
QListWidget::item:selected { background: rgba(255,255,255,0.07); }
"""


def make_metric_box(label_text: str, value_text: str, value_class: str = "") -> QFrame:
    box = QFrame()
    box.setObjectName("metric_box")
    box.setProperty("class", "metric_box")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(8, 6, 8, 6)
    layout.setSpacing(2)
    lbl = QLabel(label_text.upper())
    lbl.setProperty("class", "metric_label")
    val = QLabel(value_text)
    val.setStyleSheet("font-size: 16px; font-weight: 600;")
    if value_class:
        val.setProperty("class", value_class)
    layout.addWidget(lbl)
    layout.addWidget(val)
    box._value_label = val  # type: ignore[attr-defined]
    return box


class StackedBar(QWidget):
    """Dunne pos/neg ratio-bar."""

    def __init__(self) -> None:
        super().__init__()
        self.fraction = 0.0
        self.setFixedHeight(8)

    def set_pos(self, fraction: float) -> None:
        self.fraction = max(0.0, min(1.0, fraction))
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#2c2c2e"))
        p.drawRoundedRect(0, 0, w, h, h / 2, h / 2)
        if w <= 0:
            return
        pos_w = int(w * self.fraction)
        if pos_w > 0:
            p.setBrush(QColor("#34c759"))
            p.drawRoundedRect(0, 0, pos_w, h, h / 2, h / 2)
        if pos_w < w:
            p.setBrush(QColor("#ff3b30"))
            p.drawRoundedRect(pos_w, 0, w - pos_w, h, h / 2, h / 2)


class HoldButton(QPushButton):
    """Press-and-hold knop met progress-ring; vuurt na 2s vasthouden."""

    held = Signal()

    def __init__(self, label: str, object_name: str) -> None:
        super().__init__(label)
        self.setObjectName(object_name)
        self._progress = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._start_t = 0.0

    def mousePressEvent(self, e) -> None:  # noqa: N802
        self._start_t = time.time()
        self._progress = 0.0
        self._timer.start(50)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        self._cancel()
        super().mouseReleaseEvent(e)

    def leaveEvent(self, e) -> None:  # noqa: N802
        self._cancel()
        super().leaveEvent(e)

    def _cancel(self) -> None:
        self._timer.stop()
        self._progress = 0.0
        self.update()

    def _tick(self) -> None:
        elapsed = time.time() - self._start_t
        self._progress = min(elapsed / 2.0, 1.0)
        self.update()
        if self._progress >= 1.0:
            self._timer.stop()
            self.held.emit()
            self._progress = 0.0

    def paintEvent(self, ev) -> None:  # noqa: N802
        super().paintEvent(ev)
        if self._progress <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(255, 255, 255, 240))
        pen.setWidth(3)
        p.setPen(pen)
        rect = self.rect().adjusted(2, 2, -2, -2)
        span = int(360 * 16 * self._progress)
        p.drawArc(rect, 90 * 16, -span)


# ====== Operator window ======
class OperatorWindow(QWidget):
    def __init__(self, edge_model: EdgeModel | None) -> None:
        super().__init__()
        self.setWindowTitle("VitaCall — alarmcentrale")
        self.resize(1100, 720)
        self.setObjectName("shell")
        self.edge_model = edge_model

        self.bus = FileBus("operator")
        self.bus.message.connect(self._on_message)

        self.audio = AudioBridge()

        self.state = "idle"
        self.caller_id = ""
        self.caller_name = ""
        self.timer_seconds = 0
        self.transcript: list[dict] = []
        self.keywords: list[dict] = []
        self.history: list[dict] = []

        self._build_ui()

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start(1000)

        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self._refresh_health)
        self._health_timer.start(3000)
        self._refresh_health()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # === Sidebar (links: stemming + signalen) ===
        admin = QWidget()
        admin.setObjectName("admin")
        admin.setFixedWidth(210)
        a = QVBoxLayout(admin)
        a.setContentsMargins(16, 22, 16, 22)
        a.setSpacing(14)

        # Stemming sectie
        a.addWidget(self._section_title("Stemming"))
        self.bar = StackedBar()
        a.addWidget(self.bar)
        self.empty_mood = QLabel("Wacht op gesprek")
        self.empty_mood.setProperty("class", "empty")
        a.addWidget(self.empty_mood)

        grid = QHBoxLayout()
        grid.setSpacing(6)
        self.box_pos = make_metric_box("positief", "0%", "pos")
        self.box_neg = make_metric_box("negatief", "0%", "neg")
        grid.addWidget(self.box_pos)
        grid.addWidget(self.box_neg)
        a.addLayout(grid)
        grid2 = QHBoxLayout()
        grid2.setSpacing(6)
        self.box_frag = make_metric_box("fragmenten", "0")
        self.box_conf = make_metric_box("zekerheid", "0%")
        grid2.addWidget(self.box_frag)
        grid2.addWidget(self.box_conf)
        a.addLayout(grid2)

        # Signalen sectie
        a.addSpacing(8)
        a.addWidget(self._section_title("Signalen"))
        self.kw_list = QListWidget()
        self.kw_list.setMaximumHeight(220)
        a.addWidget(self.kw_list)
        self.empty_kw = QLabel("Nog geen signalen")
        self.empty_kw.setProperty("class", "empty")
        a.addWidget(self.empty_kw)

        grid3 = QHBoxLayout()
        grid3.setSpacing(6)
        self.box_urg = make_metric_box("urgentie", "0")
        self.box_med = make_metric_box("medicatie", "0")
        grid3.addWidget(self.box_urg)
        grid3.addWidget(self.box_med)
        a.addLayout(grid3)

        # Tekst-input (fallback / handmatige invoer voor demo zonder mic)
        a.addSpacing(8)
        a.addWidget(self._section_title("Handmatig fragment"))
        self.manual = QLineEdit()
        self.manual.setPlaceholderText("type wat de beller zegt en druk enter")
        self.manual.returnPressed.connect(self._submit_manual)
        a.addWidget(self.manual)

        a.addStretch(1)

        # === Center (call view) ===
        call = QWidget()
        call.setObjectName("call")
        c = QVBoxLayout(call)
        c.setContentsMargins(40, 50, 40, 50)
        c.setSpacing(16)

        topbar = QHBoxLayout()
        brand = QLabel("VitaCall  alarmcentrale")
        brand.setObjectName("brand")
        self.pill = QLabel("offline")
        self.pill.setObjectName("pill_off")
        topbar.addWidget(brand)
        topbar.addStretch(1)
        topbar.addWidget(self.pill)
        c.addLayout(topbar)

        self.caller_lbl = QLabel("Geen actieve oproep")
        self.caller_lbl.setObjectName("caller_name")
        self.caller_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caller_sub = QLabel("systeem klaar, geen actieve melding")
        self.caller_sub.setObjectName("caller_sub")
        self.caller_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c.addWidget(self.caller_lbl)
        c.addWidget(self.caller_sub)

        # Transcript scroll
        self.transcript_area = QScrollArea()
        self.transcript_area.setWidgetResizable(True)
        self.transcript_inner = QWidget()
        self.transcript_layout = QVBoxLayout(self.transcript_inner)
        self.transcript_layout.setSpacing(10)
        self.transcript_layout.addStretch(1)
        self.transcript_area.setWidget(self.transcript_inner)
        c.addWidget(self.transcript_area, 1)

        # Recente oproepen (idle-state)
        self.queue = QListWidget()
        self.queue.itemClicked.connect(self._open_history_item)
        self.queue.setMaximumHeight(180)
        c.addWidget(self.queue)

        # Actieknoppen
        actions = QHBoxLayout()
        actions.setSpacing(56)
        actions.addStretch(1)
        self.btn_decline = QPushButton("✕")
        self.btn_decline.setObjectName("decline")
        self.btn_decline.clicked.connect(self._decline)
        self.btn_accept = QPushButton("☎")
        self.btn_accept.setObjectName("accept")
        self.btn_accept.clicked.connect(self._accept)
        self.btn_end = QPushButton("✕")
        self.btn_end.setObjectName("endcall")
        self.btn_end.clicked.connect(self._end_call)
        self.idle_lbl = QLabel("☎  Wacht op binnenkomende oproep")
        self.idle_lbl.setStyleSheet(
            "background: rgba(255,255,255,0.04); color: rgba(255,255,255,0.65);"
            "padding: 18px 28px; border-radius: 16px; font-size: 15px;"
        )
        actions.addWidget(self.btn_decline)
        actions.addWidget(self.btn_accept)
        actions.addWidget(self.btn_end)
        actions.addWidget(self.idle_lbl)
        actions.addStretch(1)
        c.addLayout(actions)

        root.addWidget(admin)
        root.addWidget(call, 1)

        self._refresh_state()

    def _section_title(self, text: str) -> QLabel:
        lbl = QLabel(text.upper())
        lbl.setObjectName("section_title")
        return lbl

    def _refresh_health(self) -> None:
        up = api_health()
        if up:
            self.pill.setText("verbonden")
            self.pill.setObjectName("pill_on")
        else:
            self.pill.setText("offline")
            self.pill.setObjectName("pill_off")
        self.pill.setStyleSheet("")

    def _refresh_state(self) -> None:
        live = self.state == "live"
        incoming = self.state == "incoming"
        idle = self.state == "idle"

        if idle:
            self.caller_lbl.setText("Geen actieve oproep")
            last = self.history[0] if self.history else None
            sub = f"laatste oproep {last['time']}" if last else "systeem klaar, geen actieve melding"
            self.caller_sub.setText(sub)
        elif incoming:
            self.caller_lbl.setText(self.caller_name or "Beller")
            self.caller_sub.setText("inkomend")
        else:
            self.caller_lbl.setText(self.caller_name or "Beller")
            mins, secs = divmod(self.timer_seconds, 60)
            self.caller_sub.setText(f"{mins:02d}:{secs:02d}")

        self.btn_accept.setVisible(incoming)
        self.btn_decline.setVisible(incoming)
        self.btn_end.setVisible(live)
        self.idle_lbl.setVisible(idle)
        self.queue.setVisible(idle)
        self.transcript_area.setVisible(not idle or len(self.transcript) > 0)
        self.manual.setVisible(live or incoming)

        # Stemming-block
        n = len(self.transcript)
        pos = sum(1 for t in self.transcript if t.get("sentiment") == "positief")
        pos_pct = round(pos / n * 100) if n else 0
        neg_pct = 100 - pos_pct if n else 0
        avg_conf = round(sum(t.get("confidence", 0) for t in self.transcript) / n * 100) if n else 0
        self.bar.set_pos(pos / n if n else 0.0)
        self.box_pos._value_label.setText(f"{pos_pct}%")  # type: ignore[attr-defined]
        self.box_neg._value_label.setText(f"{neg_pct}%")  # type: ignore[attr-defined]
        self.box_frag._value_label.setText(str(n))  # type: ignore[attr-defined]
        self.box_conf._value_label.setText(f"{avg_conf}%")  # type: ignore[attr-defined]
        self.empty_mood.setVisible(n == 0)
        self.bar.setVisible(n > 0)

        urg = sum(1 for k in self.keywords if k["type"] == "urgentie")
        med = sum(1 for k in self.keywords if k["type"] == "medicatie")
        self.box_urg._value_label.setText(str(urg))  # type: ignore[attr-defined]
        self.box_med._value_label.setText(str(med))  # type: ignore[attr-defined]
        self.box_urg._value_label.setProperty("class", "neg" if urg else "")  # type: ignore[attr-defined]
        self.box_med._value_label.setProperty("class", "amb" if med else "")  # type: ignore[attr-defined]
        self.empty_kw.setVisible(len(self.keywords) == 0)
        self.kw_list.setVisible(len(self.keywords) > 0)

        # Urgentie-tint op de root
        is_urgent = any(k["type"] == "urgentie" for k in self.keywords)
        self.setProperty("class", "urgent" if is_urgent else "")
        self.style().unpolish(self)
        self.style().polish(self)

        # Recente oproepen
        self.queue.clear()
        for h in self.history:
            mins, secs = divmod(h["duration"], 60)
            tag = "  [URGENT]" if h.get("urgent") else ""
            it = QListWidgetItem(f"{h['time']}   {h['callerName']}   {mins:02d}:{secs:02d}{tag}")
            it.setData(Qt.ItemDataRole.UserRole, h)
            self.queue.addItem(it)

    def _on_tick(self) -> None:
        if self.state == "live":
            self.timer_seconds += 1
            self._refresh_state()

    # === Inkomende messages van caller ===
    def _on_message(self, msg: dict) -> None:
        t = msg.get("type")
        if t == "invite":
            self.caller_id = msg.get("callerId", "")
            self.caller_name = msg.get("callerName", "Beller")
            self.state = "incoming"
            self._refresh_state()
        elif t == "transcript" and msg.get("text"):
            self._add_transcript(msg["text"])
        elif t == "hangup":
            self._end_call(send=False)

    def _add_transcript(self, text: str) -> None:
        result = score_text(text, self.edge_model)
        if result is None:
            return
        entry = {
            "id": time.time(),
            "time": time.strftime("%H:%M"),
            "text": text,
            "sentiment": result["sentiment"],
            "confidence": result["confidence"],
            "keywords": result.get("keywords") or find_keywords(text),
            "source": result.get("source", "edge"),
        }
        self.transcript.append(entry)
        seen = {k["text"] for k in self.keywords}
        for k in entry["keywords"]:
            if k["text"] not in seen:
                self.keywords.append(k)
                seen.add(k["text"])
                lbl = QListWidgetItem(f"●  {k['text']}   {k['type']}")
                self.kw_list.addItem(lbl)
        self._append_transcript_row(entry)
        self._refresh_state()

    def _append_transcript_row(self, entry: dict) -> None:
        row = QFrame()
        row.setObjectName("row_pos" if entry["sentiment"] == "positief" else "row_neg")
        lay = QVBoxLayout(row)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(6)
        body = QLabel(entry["text"])
        body.setWordWrap(True)
        body.setStyleSheet("font-size: 15px;")
        lay.addWidget(body)
        kw_text = "  ".join(f"[{k['text']}]" for k in entry["keywords"])
        meta = QLabel(f"{entry['time']}  ·  {entry['sentiment']}  ·  {kw_text}")
        meta.setStyleSheet("font-size: 11px; color: rgba(255,255,255,0.65);")
        lay.addWidget(meta)
        self.transcript_layout.insertWidget(self.transcript_layout.count() - 1, row)
        QTimer.singleShot(50, lambda: self.transcript_area.verticalScrollBar().setValue(
            self.transcript_area.verticalScrollBar().maximum()))

    def _submit_manual(self) -> None:
        text = self.manual.text().strip()
        if not text:
            return
        self.manual.clear()
        self._add_transcript(text)
        self.bus.send({"type": "transcript", "text": text})

    def _accept(self) -> None:
        self.bus.send({"type": "accept"})
        self.audio.start()
        self.state = "live"
        self.timer_seconds = 0
        self._refresh_state()

    def _decline(self) -> None:
        self.bus.send({"type": "decline"})
        self.state = "idle"
        self.caller_id = ""
        self.caller_name = ""
        self._refresh_state()

    def _end_call(self, send: bool = True) -> None:
        if send:
            self.bus.send({"type": "hangup"})
        self.audio.stop()
        if self.transcript or self.caller_name:
            urg = any(k["type"] == "urgentie" for k in self.keywords)
            self.history.insert(0, {
                "id": time.time(),
                "time": time.strftime("%H:%M"),
                "callerName": self.caller_name or "Beller",
                "callerId": self.caller_id,
                "duration": self.timer_seconds,
                "urgent": urg,
                "transcript": list(self.transcript),
                "keywords": list(self.keywords),
            })
            self.history = self.history[:20]
        self.state = "idle"
        self.timer_seconds = 0
        self.transcript.clear()
        self.keywords.clear()
        self.kw_list.clear()
        for i in reversed(range(self.transcript_layout.count() - 1)):
            item = self.transcript_layout.itemAt(i)
            if item is None:
                continue
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self.caller_id = ""
        self.caller_name = ""
        self._refresh_state()

    def _open_history_item(self, item: QListWidgetItem) -> None:
        h = item.data(Qt.ItemDataRole.UserRole)
        if not h:
            return
        dlg = HistoryDialog(h, self)
        dlg.exec()


class HistoryDialog(QDialog):
    def __init__(self, h: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Gesprek {h['time']} — {h['callerName']}")
        self.resize(620, 540)
        self.setStyleSheet(STYLE)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 22, 22, 22)
        v.setSpacing(10)
        head = QLabel(h["callerName"])
        head.setStyleSheet("font-size: 22px; font-weight: 600;")
        mins, secs = divmod(h["duration"], 60)
        sub = QLabel(f"{h['time']} · {mins:02d}:{secs:02d} · {len(h['transcript'])} fragmenten")
        sub.setStyleSheet("color: rgba(255,255,255,0.65); font-size: 13px;")
        v.addWidget(head)
        v.addWidget(sub)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setSpacing(8)
        for m in h["transcript"]:
            row = QFrame()
            row.setObjectName("row_pos" if m["sentiment"] == "positief" else "row_neg")
            rl = QVBoxLayout(row)
            rl.setContentsMargins(16, 12, 16, 12)
            body = QLabel(m["text"])
            body.setWordWrap(True)
            body.setStyleSheet("font-size: 15px;")
            kws = "  ".join(f"[{k['text']}]" for k in m.get("keywords", []))
            meta = QLabel(f"{m['time']}  ·  {m['sentiment']}  ·  {kws}")
            meta.setStyleSheet("font-size: 11px; color: rgba(255,255,255,0.65);")
            rl.addWidget(body)
            rl.addWidget(meta)
            il.addWidget(row)
        il.addStretch(1)
        scroll.setWidget(inner)
        v.addWidget(scroll, 1)
        close = QPushButton("Sluiten")
        close.clicked.connect(self.accept)
        close.setStyleSheet(
            "background: #2c2c2e; padding: 10px 18px; border-radius: 10px; font-weight: 600;"
        )
        v.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)


# ====== Mobile (caller) ======
class MobileWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VitaCall — beller")
        self.resize(420, 720)
        self.setObjectName("shell")

        self.bus = FileBus("caller")
        self.bus.message.connect(self._on_message)

        self.audio = AudioBridge()
        self.state = "idle"
        self.timer_seconds = 0
        self._build_ui()

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start(1000)

    def _build_ui(self) -> None:
        self.setObjectName("mobile")
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 40, 28, 40)
        root.setSpacing(0)

        # Top: VitaCall brand top-left
        top_lbl = QLabel("VitaCall")
        top_lbl.setObjectName("brand")
        sub_lbl = QLabel("alarmcentrale")
        sub_lbl.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 12px;")
        root.addWidget(top_lbl)
        root.addWidget(sub_lbl)
        root.addSpacing(32)

        # Hero: big title + amber subtitle
        self.title = QLabel("Hulp nodig?")
        self.title.setStyleSheet("font-size: 48px; font-weight: 700; letter-spacing: -1px;")
        root.addWidget(self.title)

        self.sub = QLabel("alarmcentrale")
        self.sub.setStyleSheet("font-size: 16px; color: #ff9f0a; font-weight: 600;")
        root.addWidget(self.sub)
        root.addSpacing(12)

        self.info = QLabel("Verbonden met centrale\nGemiddelde wachttijd: 12 seconden")
        self.info.setStyleSheet("font-size: 13px; color: rgba(255,255,255,0.45); line-height: 1.5;")
        root.addWidget(self.info)

        self.error = QLabel("")
        self.error.setStyleSheet(
            "background: rgba(255,59,48,0.15); color: #ff7065;"
            "padding: 8px 12px; border-radius: 8px; font-size: 13px;"
        )
        self.error.hide()
        root.addWidget(self.error)

        root.addStretch(1)

        # Tekst-input (live only)
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("typ wat je zegt en druk enter")
        self.text_input.returnPressed.connect(self._send_text)
        self.text_input.hide()
        root.addWidget(self.text_input)
        root.addSpacing(16)

        # Bottom row: hint left, button right (matches screenshot)
        self.hint = QLabel("Houd 2 seconden vast")
        self.hint.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.4);")

        self.call_btn = HoldButton("☎", "mob_call")
        self.call_btn.held.connect(self._call)
        self.end_btn = HoldButton("✕", "mob_end")
        self.end_btn.held.connect(self._hangup)
        self.end_btn.hide()

        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        bottom.addWidget(self.hint)
        bottom.addStretch(1)
        bottom.addWidget(self.call_btn)
        bottom.addWidget(self.end_btn)
        root.addLayout(bottom)

    def _on_tick(self) -> None:
        if self.state == "live":
            self.timer_seconds += 1
            mins, secs = divmod(self.timer_seconds, 60)
            self.sub.setText(f"{mins:02d}:{secs:02d}")

    def _refresh_state(self) -> None:
        if self.state == "idle":
            self.title.setText("Hulp nodig?")
            self.sub.setText("alarmcentrale")
            self.info.show()
            self.call_btn.show()
            self.end_btn.hide()
            self.text_input.hide()
        elif self.state in ("calling", "ringing"):
            self.title.setText("Verbinden")
            self.sub.setText("verbinden…" if self.state == "calling" else "overgaan…")
            self.info.hide()
            self.call_btn.hide()
            self.end_btn.show()
            self.text_input.hide()
        else:
            self.title.setText("In gesprek")
            self.info.hide()
            self.call_btn.hide()
            self.end_btn.show()
            self.text_input.show()

    def _call(self) -> None:
        self.error.hide()
        self.state = "calling"
        self._refresh_state()
        caller_id = f"#{int(time.time()) % 9000 + 1000}"
        self.bus.send({"type": "invite", "callerId": caller_id, "callerName": "Beller"})

    def _send_text(self) -> None:
        text = self.text_input.text().strip()
        if not text:
            return
        self.text_input.clear()
        self.bus.send({"type": "transcript", "text": text})

    def _on_message(self, msg: dict) -> None:
        t = msg.get("type")
        if t == "accept":
            self.state = "live"
            self.timer_seconds = 0
            self.audio.start()
            self._refresh_state()
        elif t == "decline":
            self.error.setText("afgewezen")
            self.error.show()
            self._hangup()
        elif t == "hangup":
            self._hangup()

    def _hangup(self) -> None:
        if self.state in ("live", "calling", "ringing"):
            self.bus.send({"type": "hangup"})
        self.audio.stop()
        self.state = "idle"
        self.timer_seconds = 0
        self._refresh_state()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mobile", action="store_true", help="open caller-view i.p.v. operator")
    p.add_argument("--reset", action="store_true", help="wis signaling-bestand voor schone start")
    args = p.parse_args()

    if args.reset and SIGNAL_FILE.exists():
        SIGNAL_FILE.unlink()

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)

    if args.mobile:
        w: QWidget = MobileWindow()
    else:
        edge = EdgeModel.load(LITE_MODEL_PATH)
        if edge is None:
            print(f"[warn] edge-model niet gevonden op {LITE_MODEL_PATH} — alleen cloud-scoring werkt")
        w = OperatorWindow(edge)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
