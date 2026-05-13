"""VitaCall: operator-dashboard (passief, ontvangt) + caller-screen (initieert).

    python app/ui.py              # operator-dashboard + embedded backend
    python app/ui.py --mobile     # caller (beller-scherm)
    python app/ui.py --mobile --api http://192.168.1.50:8000   # netwerk-pair

Caller belt naar operator via HTTP. Operator luistert mee via mic en stuurt
transcript-chunks naar de API; backend scoort sentiment + keywords.
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
from app.icons import make_icon_label
from app.models import EdgeModel, find_keywords, score_text
from app.signals import AudioBridge
from app.widgets import NEG, POS, PulseDot, SentimentBar, STYLE, StatCard

ROOT = Path(__file__).resolve().parent.parent
LITE_MODEL_PATH = ROOT / "models" / "sentiment_lite.json"
HEAVY_MODEL_PATH = ROOT / "models" / "sentiment_heavy.pkl"


class OperatorDashboard(QWidget):
    """Passieve operator: ziet inkomende oproep + live transcript via API."""

    def __init__(self, edge_model: EdgeModel | None, api_url: str) -> None:
        super().__init__()
        self.setWindowTitle("VitaCall, alarmcentrale")
        self.resize(1280, 800)
        self.setObjectName("shell")
        self.edge_model = edge_model
        self.api_url = api_url.rstrip("/")
        self.audio = AudioBridge(Path("/__nonexistent__"))  # alleen mic-loopback
        self.audio.transcript.connect(self._on_local_transcript)
        self.state = "idle"
        self.caller_name = "geen oproep"
        self.timer_seconds = 0
        self.urgentie_count = 0
        self.pos_count = 0
        self.neg_count = 0
        self.transcript_history: list[dict] = []
        self._last_event_count = 0
        self._build_ui()
        QTimer(self, timeout=self._tick, interval=1000).start()  # type: ignore[call-arg]
        QTimer(self, timeout=self._poll_state, interval=600).start()  # type: ignore[call-arg]
        try:
            self.audio.start()
        except Exception:
            pass

    # ---- UI ----
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(18)

        top = QHBoxLayout()
        top.setSpacing(10)
        title = QLabel("Alarmcentrale")
        title.setObjectName("page_title")
        top.addWidget(title)
        self.live_pill = QLabel("WACHT")
        self.live_pill.setObjectName("pill_idle")
        top.addWidget(self.live_pill)
        top.addStretch(1)
        export = QPushButton(" Export")
        export.setObjectName("cta_dark")
        export.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        top.addWidget(export)
        root.addLayout(top)

        stats = QHBoxLayout()
        stats.setSpacing(14)
        self.stat_state = StatCard("Status", "Idle")
        self.stat_duration = StatCard("Gespreksduur", "00:00")
        self.stat_urgentie = StatCard("Urgentie hits", "0", NEG)
        self.stat_confidence = StatCard("Sentiment confidence", "0%")
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
        self.transcript_source = QLabel("verbonden via mic")
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

        # Caller card
        cc = QFrame()
        cc.setObjectName("card")
        cl = QVBoxLayout(cc)
        cl.setContentsMargins(20, 18, 20, 18)
        cl.setSpacing(8)
        ct = QLabel("Inkomende oproep")
        ct.setObjectName("card_title")
        cl.addWidget(ct)
        self.caller_label = QLabel(self.caller_name)
        self.caller_label.setObjectName("big_value")
        cl.addWidget(self.caller_label)
        self.caller_sub = QLabel("geen actieve verbinding")
        self.caller_sub.setObjectName("card_sub")
        cl.addWidget(self.caller_sub)
        cl.addStretch(1)
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
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        root.addLayout(grid, 1)

    # ---- State polling ----
    def _poll_state(self) -> None:
        try:
            r = requests.get(f"{self.api_url}/call/state", timeout=0.7)
            if not r.ok:
                return
            st = r.json()
        except requests.RequestException:
            return
        was_active = self.state == "active"
        is_active = bool(st.get("active"))
        if is_active and not was_active:
            self.state = "active"
            self.caller_name = st.get("caller", "Onbekend")
            self.caller_label.setText(self.caller_name)
            self.caller_sub.setText("verbonden")
            self.timer_seconds = 0
            self.transcript_list.clear()
            self.alarm_list.clear()
            self.urgentie_count = 0
            self.pos_count = 0
            self.neg_count = 0
            self._last_event_count = 0
            self.live_pill.setText("LIVE")
            self.live_pill.setObjectName("pill_active")
            self.live_pill.style().unpolish(self.live_pill)
            self.live_pill.style().polish(self.live_pill)
            self.stat_state.set_value("Actief")
        elif not is_active and was_active:
            self._end_call()

        events = st.get("events", [])
        if len(events) > self._last_event_count:
            for ev in events[self._last_event_count:]:
                self._render_transcript_line(ev.get("text", ""))
            self._last_event_count = len(events)
            self._refresh_stats()

    def _end_call(self) -> None:
        self.state = "idle"
        self.caller_name = "geen oproep"
        self.caller_label.setText(self.caller_name)
        self.caller_sub.setText("geen actieve verbinding")
        self.live_pill.setText("WACHT")
        self.live_pill.setObjectName("pill_idle")
        self.live_pill.style().unpolish(self.live_pill)
        self.live_pill.style().polish(self.live_pill)
        self.stat_state.set_value("Idle")

    def _tick(self) -> None:
        if self.state == "active":
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
        """Mic-input op operator-machine? Stuur naar API zodat caller-side ook ziet."""
        if self.state != "active":
            return
        try:
            requests.post(f"{self.api_url}/call/transcript", json={"text": text}, timeout=1)
        except requests.RequestException:
            pass


class CallerScreen(QWidget):
    """iPhone-style call-scherm. Belt naar de API (operator)."""

    def __init__(self, api_url: str) -> None:
        super().__init__()
        self.setWindowTitle("VitaCall")
        self.resize(390, 780)
        self.setObjectName("mobile")
        self.api_url = api_url.rstrip("/")
        self.state = "idle"
        self.timer_seconds = 0
        self._build_ui()
        QTimer(self, timeout=self._tick, interval=1000).start()  # type: ignore[call-arg]

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 60, 32, 50)
        root.setSpacing(0)

        self.status_top = QLabel("alarmcentrale")
        self.status_top.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 15px;")
        self.status_top.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.status_top)

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

        # Eén grote actie-knop in het midden (call / hangup)
        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.call_btn = QPushButton()
        self.call_btn.setObjectName("mob_accept")
        self.call_btn.setIcon(make_icon_label("phone", 36).pixmap())
        self.call_btn.setText("")
        self._set_icon(self.call_btn, "phone", 36)
        self.call_btn.clicked.connect(self._toggle_call)
        btn_row.addWidget(self.call_btn)
        root.addLayout(btn_row)

        self.call_caption = QLabel("Bel alarmcentrale")
        self.call_caption.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 14px; font-weight: 500;")
        self.call_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addSpacing(14)
        root.addWidget(self.call_caption)

        root.addStretch(1)

    def _set_icon(self, btn: QPushButton, kind: str, size: int) -> None:
        lbl = make_icon_label(kind, size, color="#ffffff")
        btn.setIcon(lbl.pixmap())
        from PySide6.QtCore import QSize
        btn.setIconSize(QSize(size, size))

    def _toggle_call(self) -> None:
        if self.state == "idle":
            try:
                r = requests.post(f"{self.api_url}/call/start",
                                  json={"caller": "Beller"}, timeout=2)
                if not r.ok:
                    self.status_label.setText("kan operator niet bereiken")
                    return
            except requests.RequestException:
                self.status_label.setText("offline, geen verbinding")
                return
            self.state = "active"
            self.timer_seconds = 0
            self.call_btn.setObjectName("mob_decline")
            self.call_btn.style().unpolish(self.call_btn)
            self.call_btn.style().polish(self.call_btn)
            self._set_icon(self.call_btn, "phone_down", 36)
            self.call_caption.setText("Hang op")
            self.status_label.setText("verbonden")
        else:
            try:
                requests.post(f"{self.api_url}/call/end", timeout=2)
            except requests.RequestException:
                pass
            self.state = "idle"
            self.timer_seconds = 0
            self.call_btn.setObjectName("mob_accept")
            self.call_btn.style().unpolish(self.call_btn)
            self.call_btn.style().polish(self.call_btn)
            self._set_icon(self.call_btn, "phone", 36)
            self.call_caption.setText("Bel alarmcentrale")
            self.status_label.setText("klaar om te bellen")

    def _tick(self) -> None:
        if self.state == "active":
            self.timer_seconds += 1
            m, s = divmod(self.timer_seconds, 60)
            self.status_label.setText(f"{m:02}:{s:02}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mobile", action="store_true", help="open beller-scherm")
    parser.add_argument("--no-server", action="store_true", help="start geen embedded backend")
    parser.add_argument("--api", default="http://127.0.0.1:8000",
                        help="API-URL (override voor netwerk-gebruik)")
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
