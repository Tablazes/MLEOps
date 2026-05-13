"""VitaCall desktop UI: operator-dashboard + iPhone-style call-screen voor beller.

    python app/ui.py              # operator-dashboard + embedded backend
    python app/ui.py --mobile     # beller-call-screen
    python app/ui.py --no-server  # operator zonder backend (extern uvicorn)

Geen text-input meer: transcript komt van speech-to-text (Vosk-NL).
Zonder Vosk wordt een demo-script afgespeeld zodat de UI altijd iets toont.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.backend import start_api_server
from app.models import EdgeModel, api_health, find_keywords, score_text
from app.signals import AudioBridge, FileBus
from app.widgets import (
    ACCENT,
    IconButton,
    NEG,
    POS,
    PulseDot,
    SentimentBar,
    STYLE,
    StatCard,
)

ROOT = Path(__file__).resolve().parent.parent
LITE_MODEL_PATH = ROOT / "models" / "sentiment_lite.json"
HEAVY_MODEL_PATH = ROOT / "models" / "sentiment_heavy.pkl"
SIGNAL_FILE = ROOT / "signaling.json"
VOSK_DIR = ROOT / "models" / "vosk-nl"

DEMO_LINES = [
    "hallo dit is de alarmcentrale",
    "ik heb mijn moeder net gevonden",
    "zij ligt op de grond",
    "ze ademt heel zwaar",
    "ik heb pijn op de borst",
    "ze is bewusteloos",
    "het lijkt op een hartaanval",
    "ze heeft bloedverdunners",
]


class OperatorDashboard(QWidget):
    """Operator-dashboard met live transcript, sentiment, stats en alarmen."""

    def __init__(self, edge_model: EdgeModel | None) -> None:
        super().__init__()
        self.setWindowTitle("VitaCall, alarmcentrale dashboard")
        self.resize(1280, 800)
        self.setObjectName("shell")
        self.edge_model = edge_model
        self.bus = FileBus("operator", SIGNAL_FILE)
        self.bus.message.connect(self._on_bus_message)
        self.audio = AudioBridge(VOSK_DIR)
        self.state = "idle"
        self.caller_id = "anoniem"
        self.timer_seconds = 0
        self.transcript: list[dict] = []
        self.urgentie_count = 0
        self.medicatie_count = 0
        self.pos_count = 0
        self.neg_count = 0
        self._demo_idx = 0
        self._build_ui()
        QTimer(self, timeout=self._tick, interval=1000).start()  # type: ignore[call-arg]
        QTimer(self, timeout=self._refresh_health, interval=3000).start()  # type: ignore[call-arg]
        self._refresh_health()
        self._start_audio_or_demo()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(18)

        # Topbar
        top = QHBoxLayout()
        top.setSpacing(12)
        title = QLabel("Alarmcentrale")
        title.setObjectName("page_title")
        top.addWidget(title)
        active = QLabel("Live")
        active.setObjectName("pill_active")
        top.addWidget(active)
        top.addStretch(1)
        self.health_pill = QLabel("CLOUD")
        self.health_pill.setObjectName("pill_ok")
        top.addWidget(self.health_pill)
        export_btn = QPushButton("Export")
        export_btn.setObjectName("cta_dark")
        top.addWidget(export_btn)
        root.addLayout(top)

        # Stats row: 4 stat-cards
        stats = QHBoxLayout()
        stats.setSpacing(14)
        self.stat_calls = StatCard("Actieve gesprekken", "1", ACCENT)
        self.stat_duration = StatCard("Gespreksduur", "00:00")
        self.stat_urgentie = StatCard("Urgentie-keywords", "0", NEG)
        self.stat_confidence = StatCard("Sentiment confidence", "0%")
        stats.addWidget(self.stat_calls)
        stats.addWidget(self.stat_duration)
        stats.addWidget(self.stat_urgentie)
        stats.addWidget(self.stat_confidence)
        root.addLayout(stats)

        # Main grid: live transcript (links) + alarmen + caller (rechts)
        grid = QGridLayout()
        grid.setSpacing(14)

        # Live transcript card
        transcript_card = QFrame()
        transcript_card.setObjectName("card")
        tl = QVBoxLayout(transcript_card)
        tl.setContentsMargins(20, 18, 20, 18)
        tl.setSpacing(10)
        th = QHBoxLayout()
        th.setSpacing(8)
        self.pulse = PulseDot()
        th.addWidget(self.pulse)
        tt = QLabel("Live transcript")
        tt.setObjectName("card_title")
        th.addWidget(tt)
        th.addStretch(1)
        self.transcript_source = QLabel("speech-to-text")
        self.transcript_source.setObjectName("card_sub")
        th.addWidget(self.transcript_source)
        tl.addLayout(th)
        self.transcript_list = QListWidget()
        self.transcript_list.setFrameShape(QFrame.Shape.NoFrame)
        tl.addWidget(self.transcript_list, 1)

        # Sentiment bar onder de transcript
        sb_label = QLabel("Stemming pos/neg")
        sb_label.setObjectName("stat_label")
        tl.addWidget(sb_label)
        self.sentiment_bar = SentimentBar()
        tl.addWidget(self.sentiment_bar)

        grid.addWidget(transcript_card, 0, 0, 2, 1)

        # Caller-info card
        caller_card = QFrame()
        caller_card.setObjectName("card")
        cl = QVBoxLayout(caller_card)
        cl.setContentsMargins(20, 18, 20, 18)
        cl.setSpacing(8)
        ct = QLabel("Beller")
        ct.setObjectName("card_title")
        cl.addWidget(ct)
        self.caller_label = QLabel(self.caller_id)
        self.caller_label.setObjectName("big_value")
        cl.addWidget(self.caller_label)
        cs = QLabel("Inkomende oproep · regio onbekend")
        cs.setObjectName("card_sub")
        cl.addWidget(cs)
        cl.addStretch(1)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        accept = QPushButton("Accepteer")
        accept.setObjectName("cta_accent")
        accept.clicked.connect(lambda: self._set_state("active"))
        decline = QPushButton("Hang op")
        decline.setObjectName("cta_dark")
        decline.clicked.connect(lambda: self._set_state("idle"))
        actions.addWidget(accept)
        actions.addWidget(decline)
        cl.addLayout(actions)
        grid.addWidget(caller_card, 0, 1)

        # Alarmen card
        alarm_card = QFrame()
        alarm_card.setObjectName("card")
        al = QVBoxLayout(alarm_card)
        al.setContentsMargins(20, 18, 20, 18)
        al.setSpacing(10)
        ah = QHBoxLayout()
        at = QLabel("Actieve alarmen")
        at.setObjectName("card_title")
        ah.addWidget(at)
        ah.addStretch(1)
        ahmeta = QLabel("urgentie & medicatie")
        ahmeta.setObjectName("card_sub")
        ah.addWidget(ahmeta)
        al.addLayout(ah)
        self.alarm_list = QListWidget()
        self.alarm_list.setFrameShape(QFrame.Shape.NoFrame)
        al.addWidget(self.alarm_list, 1)
        grid.addWidget(alarm_card, 1, 1)

        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        root.addLayout(grid, 1)

    def _set_state(self, state: str) -> None:
        self.state = state
        if state == "idle":
            self.timer_seconds = 0
            self.transcript.clear()
            self.transcript_list.clear()
            self.alarm_list.clear()
            self.urgentie_count = 0
            self.pos_count = 0
            self.neg_count = 0

    def _tick(self) -> None:
        if self.state == "active":
            self.timer_seconds += 1
            m, s = divmod(self.timer_seconds, 60)
            self.stat_duration.set_value(f"{m:02}:{s:02}")
        self._refresh_stats()
        self._maybe_advance_demo()

    def _refresh_health(self) -> None:
        ok = api_health()
        self.health_pill.setText("CLOUD" if ok else "EDGE")
        self.health_pill.setObjectName("pill_ok" if ok else "pill_off")
        self.health_pill.style().unpolish(self.health_pill)
        self.health_pill.style().polish(self.health_pill)

    def _refresh_stats(self) -> None:
        self.stat_calls.set_value("1" if self.state == "active" else "0")
        self.stat_urgentie.set_value(str(self.urgentie_count))
        total = self.pos_count + self.neg_count
        if total > 0:
            confs = [t.get("confidence", 0) for t in self.transcript if t.get("confidence")]
            avg = (sum(confs) / len(confs)) if confs else 0
            self.stat_confidence.set_value(f"{int(avg * 100)}%")
            self.sentiment_bar.set_pos(self.pos_count / total)
        else:
            self.stat_confidence.set_value("0%")

    def _on_bus_message(self, msg: dict) -> None:
        if msg.get("event") == "call_request":
            self.caller_id = msg.get("caller", "anoniem")
            self.caller_label.setText(self.caller_id)
            self._set_state("active")
            self._demo_idx = 0

    # Audio of demo
    def _start_audio_or_demo(self) -> None:
        if VOSK_DIR.exists():
            self.audio.transcript.connect(self._on_audio_chunk)
            self.audio.start()
            self.transcript_source.setText("Vosk live")
        else:
            self.transcript_source.setText("demo (geen Vosk-NL)")

    def _on_audio_chunk(self, text: str) -> None:
        self._process_utterance(text)

    def _maybe_advance_demo(self) -> None:
        if VOSK_DIR.exists() or self.state != "active":
            return
        if self.timer_seconds and self.timer_seconds % 3 == 0:
            if self._demo_idx < len(DEMO_LINES):
                self._process_utterance(DEMO_LINES[self._demo_idx])
                self._demo_idx += 1

    def _process_utterance(self, text: str) -> None:
        result = score_text(text, self.edge_model) or {}
        sentiment = result.get("sentiment", "?")
        confidence = result.get("confidence", 0.0)
        kws = result.get("keywords") or find_keywords(text)
        row = {"text": text, "sentiment": sentiment, "confidence": confidence, "keywords": kws,
               "time": datetime.now().strftime("%H:%M:%S")}
        self.transcript.append(row)
        if sentiment == "positief":
            self.pos_count += 1
        elif sentiment == "negatief":
            self.neg_count += 1

        # transcript-row
        emoji = "🟢" if sentiment == "positief" else ("🔴" if sentiment == "negatief" else "⚪")
        kw_str = " · ".join(k["text"] for k in kws[:3])
        line = f"{row['time']}   {emoji}  {text}"
        if kw_str:
            line += f"    [{kw_str}]"
        item = QListWidgetItem(line)
        if sentiment == "negatief":
            item.setForeground(Qt.GlobalColor.darkRed)
        self.transcript_list.addItem(item)
        self.transcript_list.scrollToBottom()

        # alarms
        for kw in kws:
            if kw["type"] == "urgentie":
                self.urgentie_count += 1
                a = QListWidgetItem(f"⚠  {kw['text'].upper()}    {row['time']}")
                a.setForeground(Qt.GlobalColor.red)
                self.alarm_list.addItem(a)
            elif kw["type"] == "medicatie":
                a = QListWidgetItem(f"💊  {kw['text']}    {row['time']}")
                self.alarm_list.addItem(a)
        self.alarm_list.scrollToBottom()


# iPhone-style call screen voor de beller
class MobileCallScreen(QWidget):
    """iPhone-style inkomende-oproep scherm met decline/accept onderaan."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VitaCall, beller")
        self.resize(390, 780)
        self.setObjectName("mobile")
        self.bus = FileBus("mobile", SIGNAL_FILE)
        self.state = "idle"
        self.timer_seconds = 0
        self._build_ui()
        QTimer(self, timeout=self._tick, interval=1000).start()  # type: ignore[call-arg]

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 60, 28, 50)
        root.setSpacing(0)

        top_label = QLabel("Inkomende oproep")
        top_label.setProperty("class", "mob_label")
        top_label.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 16px; font-weight: 500;")
        top_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(top_label)

        root.addSpacing(14)

        self.caller_label = QLabel("VitaCall 112")
        self.caller_label.setStyleSheet("color: white; font-size: 38px; font-weight: 600; letter-spacing: -1px;")
        self.caller_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.caller_label)

        self.status_label = QLabel("alarmcentrale")
        self.status_label.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 16px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.status_label)

        root.addStretch(1)

        # Onderste actie-rij
        self.subtitle = QLabel("Klik groen om te bellen")
        self.subtitle.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 17px;")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.subtitle)

        root.addSpacing(20)

        btns = QHBoxLayout()
        btns.setSpacing(60)
        btns.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.decline_btn = QPushButton("✕")
        self.decline_btn.setObjectName("mob_decline")
        self.decline_btn.clicked.connect(self._on_decline)
        self.accept_btn = QPushButton("📞")
        self.accept_btn.setObjectName("mob_accept")
        self.accept_btn.clicked.connect(self._on_accept)
        btns.addWidget(self.decline_btn)
        btns.addWidget(self.accept_btn)
        root.addLayout(btns)

        labels = QHBoxLayout()
        labels.setSpacing(60)
        labels.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dl = QLabel("Decline")
        dl.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 12px;")
        dl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        al = QLabel("Accept")
        al.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 12px;")
        al.setAlignment(Qt.AlignmentFlag.AlignCenter)
        labels.addWidget(dl)
        labels.addWidget(al)
        root.addLayout(labels)

    def _on_accept(self) -> None:
        self.state = "active"
        self.timer_seconds = 0
        self.bus.send({"event": "call_request", "caller": "Beller VitaCall"})
        self.caller_label.setText("VitaCall 112")
        self.subtitle.setText("In gesprek")

    def _on_decline(self) -> None:
        self.state = "idle"
        self.timer_seconds = 0
        self.subtitle.setText("Opgehangen")

    def _tick(self) -> None:
        if self.state == "active":
            self.timer_seconds += 1
            m, s = divmod(self.timer_seconds, 60)
            self.status_label.setText(f"{m:02}:{s:02}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mobile", action="store_true", help="open beller-call-screen")
    parser.add_argument("--no-server", action="store_true", help="start geen embedded backend")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)

    if args.mobile:
        win: QWidget = MobileCallScreen()
    else:
        if not args.no_server:
            start_api_server(HEAVY_MODEL_PATH, "http://127.0.0.1:8000")
            time.sleep(1)
        edge = EdgeModel.load(LITE_MODEL_PATH)
        win = OperatorDashboard(edge)

    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
