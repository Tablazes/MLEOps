"""VitaCall: operator-dashboard + caller-screen, beide via HTTP-call-flow.

Flow:
  caller → POST /call/start   (state: ringing)
  operator → ziet ringing → klikt Opnemen → POST /call/accept (state: active)
                              ↓
  operator-mic → Vosk-NL chunks → POST /call/transcript
                              ↓
  beide kanten pollen /call/state → tonen synchroon
  beide kanten kunnen ophangen → POST /call/end

    python app/ui.py                                  # operator
    python app/ui.py --mobile                         # caller (zelfde machine)
    python app/ui.py --mobile --api http://<ip>:8000  # caller via netwerk
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

import requests
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.backend import start_api_server
from app.icons import icon_size, qicon
from app.models import EdgeModel, find_keywords, score_text
from app.signals import AudioBridge
from app.widgets import NEG, POS, PulseDot, SentimentBar, STYLE, StatCard

ROOT = Path(__file__).resolve().parent.parent
LITE_MODEL_PATH = ROOT / "models" / "sentiment_lite.json"
HEAVY_MODEL_PATH = ROOT / "models" / "sentiment_heavy.pkl"
VOSK_DIR = ROOT / "models" / "vosk-nl"


class OperatorDashboard(QWidget):
    def __init__(self, edge_model: EdgeModel | None, api_url: str) -> None:
        super().__init__()
        self.setWindowTitle("VitaCall, alarmcentrale")
        self.resize(1280, 800)
        self.setObjectName("shell")
        self.edge_model = edge_model
        self.api_url = api_url.rstrip("/")
        self.audio = AudioBridge(VOSK_DIR)
        self.audio.transcript.connect(self._on_local_transcript)
        self._audio_started = False
        self.phase = "idle"
        self.caller_name = ""
        self.timer_seconds = 0
        self.urgentie_count = 0
        self.pos_count = 0
        self.neg_count = 0
        self.transcript_history: list[dict] = []
        self._last_event_count = 0
        self._build_ui()
        QTimer(self, timeout=self._tick, interval=1000).start()  # type: ignore[call-arg]
        QTimer(self, timeout=self._poll_state, interval=500).start()  # type: ignore[call-arg]

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(18)

        top = QHBoxLayout()
        top.setSpacing(10)
        title = QLabel("Alarmcentrale")
        title.setObjectName("page_title")
        top.addWidget(title)
        self.phase_pill = QLabel("WACHT")
        self.phase_pill.setObjectName("pill_idle")
        top.addWidget(self.phase_pill)
        top.addStretch(1)
        export = QPushButton(" Export")
        export.setObjectName("cta_dark")
        export.setIcon(qicon("export", "white"))
        export.setIconSize(icon_size(14))
        top.addWidget(export)
        root.addLayout(top)

        stats = QHBoxLayout()
        stats.setSpacing(14)
        self.stat_state = StatCard("Status", "Idle")
        self.stat_duration = StatCard("Gespreksduur", "00:00")
        self.stat_urgentie = StatCard("Urgentie hits", "0", NEG)
        self.stat_confidence = StatCard("Confidence", "0%")
        stats.addWidget(self.stat_state)
        stats.addWidget(self.stat_duration)
        stats.addWidget(self.stat_urgentie)
        stats.addWidget(self.stat_confidence)
        root.addLayout(stats)

        grid = QGridLayout()
        grid.setSpacing(14)

        # Transcript card
        tc = QFrame()
        tc.setObjectName("card")
        tl = QVBoxLayout(tc)
        tl.setContentsMargins(20, 18, 20, 18)
        tl.setSpacing(10)
        th = QHBoxLayout()
        th.setSpacing(10)
        self.pulse = PulseDot()
        th.addWidget(self.pulse)
        tt = QLabel("Live transcript")
        tt.setObjectName("card_title")
        th.addWidget(tt)
        th.addStretch(1)
        self.transcript_source = QLabel("idle")
        self.transcript_source.setObjectName("card_sub")
        th.addWidget(self.transcript_source)
        tl.addLayout(th)
        self.transcript_list = QListWidget()
        self.transcript_list.setFrameShape(QFrame.Shape.NoFrame)
        tl.addWidget(self.transcript_list, 1)
        sb_label = QLabel("Stemming pos/neg")
        sb_label.setObjectName("stat_label")
        tl.addWidget(sb_label)
        self.sentiment_bar = SentimentBar()
        tl.addWidget(self.sentiment_bar)
        grid.addWidget(tc, 0, 0, 2, 1)

        # Caller card met Accept-knop
        cc = QFrame()
        cc.setObjectName("card")
        cl = QVBoxLayout(cc)
        cl.setContentsMargins(20, 18, 20, 18)
        cl.setSpacing(8)
        ct = QLabel("Beller")
        ct.setObjectName("card_title")
        cl.addWidget(ct)
        self.caller_label = QLabel("geen oproep")
        self.caller_label.setObjectName("big_value")
        cl.addWidget(self.caller_label)
        self.caller_sub = QLabel("wacht op binnenkomende oproep")
        self.caller_sub.setObjectName("card_sub")
        cl.addWidget(self.caller_sub)
        cl.addStretch(1)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.accept_btn = QPushButton(" Opnemen")
        self.accept_btn.setObjectName("cta_accent")
        self.accept_btn.setIcon(qicon("phone", "#0a0a0c"))
        self.accept_btn.setIconSize(icon_size(14))
        self.accept_btn.clicked.connect(self._on_accept)
        self.accept_btn.setEnabled(False)
        self.end_btn = QPushButton(" Ophangen")
        self.end_btn.setObjectName("cta_dark")
        self.end_btn.setIcon(qicon("phone_down", "white"))
        self.end_btn.setIconSize(icon_size(14))
        self.end_btn.clicked.connect(self._on_end)
        self.end_btn.setEnabled(False)
        actions.addWidget(self.accept_btn)
        actions.addWidget(self.end_btn)
        cl.addLayout(actions)
        grid.addWidget(cc, 0, 1)

        # Alarm card
        ac = QFrame()
        ac.setObjectName("card")
        al = QVBoxLayout(ac)
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
        grid.addWidget(ac, 1, 1)

        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 1)
        root.addLayout(grid, 1)

    # ---- HTTP polling ----
    def _poll_state(self) -> None:
        try:
            r = requests.get(f"{self.api_url}/call/state", timeout=0.7)
            if not r.ok:
                return
            st = r.json()
        except requests.RequestException:
            return
        new_phase = st.get("phase", "idle")
        if new_phase != self.phase:
            self._phase_change(new_phase, st.get("caller", ""))
        events = st.get("events", [])
        if len(events) > self._last_event_count and self.phase == "active":
            for ev in events[self._last_event_count:]:
                self._render_transcript_line(ev.get("text", ""))
            self._last_event_count = len(events)
            self._refresh_stats()

    def _phase_change(self, new_phase: str, caller: str) -> None:
        self.phase = new_phase
        if new_phase == "ringing":
            self.caller_name = caller or "Onbekende beller"
            self.caller_label.setText(self.caller_name)
            self.caller_sub.setText("RINGING, neem op")
            self.accept_btn.setEnabled(True)
            self.end_btn.setEnabled(True)
            self.phase_pill.setText("BELLEN")
            self.phase_pill.setObjectName("pill_idle")
            self.stat_state.set_value("Ringing")
            self.transcript_source.setText("wacht op opnemen")
        elif new_phase == "active":
            self.caller_sub.setText("verbonden")
            self.accept_btn.setEnabled(False)
            self.end_btn.setEnabled(True)
            self.phase_pill.setText("LIVE")
            self.phase_pill.setObjectName("pill_active")
            self.stat_state.set_value("Actief")
            self.timer_seconds = 0
            self.transcript_list.clear()
            self.alarm_list.clear()
            self.urgentie_count = 0
            self.pos_count = 0
            self.neg_count = 0
            self._last_event_count = 0
            self._start_audio_if_needed()
        else:  # idle
            self.caller_name = ""
            self.caller_label.setText("geen oproep")
            self.caller_sub.setText("wacht op binnenkomende oproep")
            self.accept_btn.setEnabled(False)
            self.end_btn.setEnabled(False)
            self.phase_pill.setText("WACHT")
            self.phase_pill.setObjectName("pill_idle")
            self.stat_state.set_value("Idle")
            self.transcript_source.setText("idle")
        # Force stylesheet re-apply
        self.phase_pill.style().unpolish(self.phase_pill)
        self.phase_pill.style().polish(self.phase_pill)

    def _start_audio_if_needed(self) -> None:
        if self._audio_started:
            self.transcript_source.setText("Vosk-NL live")
            return
        try:
            started = self.audio.start()
        except Exception:
            started = False
        self._audio_started = started
        self.transcript_source.setText("Vosk-NL live" if started else "geen mic")

    # ---- Acties ----
    def _on_accept(self) -> None:
        try:
            requests.post(f"{self.api_url}/call/accept", timeout=2)
        except requests.RequestException:
            pass

    def _on_end(self) -> None:
        try:
            requests.post(f"{self.api_url}/call/end", timeout=2)
        except requests.RequestException:
            pass

    def _tick(self) -> None:
        if self.phase == "active":
            self.timer_seconds += 1
            m, s = divmod(self.timer_seconds, 60)
            self.stat_duration.set_value(f"{m:02}:{s:02}")

    def _refresh_stats(self) -> None:
        self.stat_urgentie.set_value(str(self.urgentie_count))
        total = self.pos_count + self.neg_count
        if total > 0:
            confs = [t.get("confidence", 0) for t in self.transcript_history if t.get("confidence")]
            avg = (sum(confs) / len(confs)) if confs else 0
            self.stat_confidence.set_value(f"{int(avg * 100)}%")
            self.sentiment_bar.set_pos(self.pos_count / total)
        else:
            self.stat_confidence.set_value("0%")
            self.sentiment_bar.set_pos(0.5)

    def _render_transcript_line(self, text: str) -> None:
        if not text:
            return
        result = score_text(text, self.edge_model) or {}
        sentiment = result.get("sentiment", "?")
        confidence = result.get("confidence", 0.0)
        kws = result.get("keywords") or find_keywords(text)
        row = {"text": text, "sentiment": sentiment, "confidence": confidence,
               "keywords": kws, "time": datetime.now().strftime("%H:%M:%S")}
        self.transcript_history.append(row)
        if sentiment == "positief":
            self.pos_count += 1
        elif sentiment == "negatief":
            self.neg_count += 1

        kw_str = "  ".join(f"#{k['text']}" for k in kws[:3])
        line = f"  {row['time']}    {text}"
        if kw_str:
            line += f"     {kw_str}"
        item = QListWidgetItem(line)
        if sentiment == "negatief":
            item.setForeground(QColor("#ff6b6b"))
        elif sentiment == "positief":
            item.setForeground(QColor("#34d399"))
        else:
            item.setForeground(QColor("#d4d4d8"))
        self.transcript_list.addItem(item)
        self.transcript_list.scrollToBottom()

        for kw in kws:
            if kw["type"] == "urgentie":
                self.urgentie_count += 1
                a = QListWidgetItem(f"  {kw['text'].upper()}        {row['time']}")
                a.setForeground(QColor("#ff6b6b"))
                self.alarm_list.addItem(a)
            elif kw["type"] == "medicatie":
                a = QListWidgetItem(f"  {kw['text']}        {row['time']}")
                a.setForeground(QColor("#fbbf24"))
                self.alarm_list.addItem(a)
        self.alarm_list.scrollToBottom()

    def _on_local_transcript(self, text: str) -> None:
        if self.phase != "active":
            return
        try:
            requests.post(f"{self.api_url}/call/transcript",
                          json={"text": text}, timeout=1)
        except requests.RequestException:
            pass


class CallerScreen(QWidget):
    """Eenvoudig caller-scherm: één call-knop, sync met operator-state."""

    def __init__(self, api_url: str) -> None:
        super().__init__()
        self.setWindowTitle("VitaCall")
        self.resize(390, 780)
        self.setObjectName("mobile")
        self.api_url = api_url.rstrip("/")
        self.phase = "idle"
        self.timer_seconds = 0
        self._build_ui()
        QTimer(self, timeout=self._tick, interval=1000).start()  # type: ignore[call-arg]
        QTimer(self, timeout=self._poll_state, interval=500).start()  # type: ignore[call-arg]

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 60, 32, 50)
        root.setSpacing(0)

        self.top_label = QLabel("alarmcentrale")
        self.top_label.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 15px;")
        self.top_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.top_label)

        root.addSpacing(8)

        self.caller_label = QLabel("VitaCall")
        self.caller_label.setStyleSheet("color: white; font-size: 44px; font-weight: 600; letter-spacing: -1.2px;")
        self.caller_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.caller_label)

        self.status_label = QLabel("klaar om te bellen")
        self.status_label.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 14px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.status_label)

        root.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.call_btn = QPushButton()
        self.call_btn.setObjectName("mob_accept")
        self.call_btn.setIcon(qicon("phone", "white"))
        self.call_btn.setIconSize(icon_size(28))
        self.call_btn.clicked.connect(self._toggle_call)
        btn_row.addWidget(self.call_btn)
        root.addLayout(btn_row)

        self.call_caption = QLabel("Bel alarmcentrale")
        self.call_caption.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 14px; font-weight: 500;")
        self.call_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addSpacing(14)
        root.addWidget(self.call_caption)

        root.addStretch(1)

    def _toggle_call(self) -> None:
        if self.phase == "idle":
            try:
                requests.post(f"{self.api_url}/call/start", json={"caller": "Beller"}, timeout=2)
            except requests.RequestException:
                self.status_label.setText("offline")
                return
        else:
            try:
                requests.post(f"{self.api_url}/call/end", timeout=2)
            except requests.RequestException:
                pass

    def _poll_state(self) -> None:
        try:
            r = requests.get(f"{self.api_url}/call/state", timeout=0.7)
            if not r.ok:
                return
            st = r.json()
        except requests.RequestException:
            self.status_label.setText("geen verbinding")
            return
        new_phase = st.get("phase", "idle")
        if new_phase != self.phase:
            self.phase = new_phase
            self.timer_seconds = 0
            if new_phase == "ringing":
                self.status_label.setText("aan het bellen...")
                self.call_btn.setObjectName("mob_decline")
                self.call_btn.setIcon(qicon("phone_down", "white"))
                self.call_caption.setText("Ophangen")
            elif new_phase == "active":
                self.status_label.setText("verbonden")
                self.call_btn.setObjectName("mob_decline")
                self.call_btn.setIcon(qicon("phone_down", "white"))
                self.call_caption.setText("Ophangen")
            else:
                self.status_label.setText("klaar om te bellen")
                self.call_btn.setObjectName("mob_accept")
                self.call_btn.setIcon(qicon("phone", "white"))
                self.call_caption.setText("Bel alarmcentrale")
            self.call_btn.style().unpolish(self.call_btn)
            self.call_btn.style().polish(self.call_btn)

    def _tick(self) -> None:
        if self.phase == "active":
            self.timer_seconds += 1
            m, s = divmod(self.timer_seconds, 60)
            self.status_label.setText(f"{m:02}:{s:02}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mobile", action="store_true")
    parser.add_argument("--no-server", action="store_true")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)

    if args.mobile:
        win: QWidget = CallerScreen(args.api)
    else:
        if not args.no_server:
            start_api_server(HEAVY_MODEL_PATH, args.api)
            time.sleep(1)
        edge = EdgeModel.load(LITE_MODEL_PATH)
        win = OperatorDashboard(edge, args.api)

    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
