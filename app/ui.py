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
from app.widgets import (
    ACCENT,
    AvatarTile,
    GradientContactCard,
    NEG,
    POS,
    SentimentBar,
    STYLE,
    StatCard,
    TEXT,
    TEXT_DIM,
    TrafficLights,
    WARN,
    _initials,
)

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
        self.audio.partial.connect(self._on_local_partial)
        self._audio_started = False
        self._current_call_id = 0
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
        QTimer(self, timeout=self._poll_state, interval=400).start()  # type: ignore[call-arg]
        QTimer(self, timeout=self._poll_history, interval=2000).start()  # type: ignore[call-arg]
        self._poll_history()

    def _build_ui(self) -> None:
        # Bureaublad-achtergrond; het 'venster' zweeft erin (Tahoe-look).
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        window = QFrame()
        window.setObjectName("window")
        outer.addWidget(window)

        root = QVBoxLayout(window)
        root.setContentsMargins(18, 14, 18, 16)
        root.setSpacing(14)

        # ---- Toolbar: traffic-lights · Edit · sort | grid · zoek ----
        bar = QHBoxLayout()
        bar.setSpacing(10)
        bar.addWidget(TrafficLights())
        bar.addSpacing(8)
        edit_btn = QPushButton("Edit")
        edit_btn.setObjectName("tool")
        bar.addWidget(edit_btn)
        sort_btn = QPushButton("☰")
        sort_btn.setObjectName("tool")
        bar.addWidget(sort_btn)
        bar.addStretch(1)
        self.phase_pill = QLabel("WACHT")
        self.phase_pill.setObjectName("pill_idle")
        bar.addWidget(self.phase_pill)
        grid_btn = QPushButton("▦")
        grid_btn.setObjectName("tool")
        bar.addWidget(grid_btn)
        search = QLabel("  ⌕  Zoeken")
        search.setObjectName("search")
        search.setFixedWidth(160)
        bar.addWidget(search)
        root.addLayout(bar)

        # ---- Avatar-tegelrij (favoriete/recente bellers) ----
        self.tiles_row = QHBoxLayout()
        self.tiles_row.setSpacing(14)
        self.tiles_row.setContentsMargins(2, 2, 2, 2)
        self.tiles_row.addStretch(1)
        self._rebuild_tiles([])
        root.addLayout(self.tiles_row)

        # ---- Hoofdsplit: links recents/transcript, rechts contactkaart ----
        split = QHBoxLayout()
        split.setSpacing(16)

        # LINKS, sidebar met "Recents" kop + stat-strip + transcript-lijst
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(18, 16, 18, 16)
        sl.setSpacing(12)

        rec_head = QHBoxLayout()
        rec_title = QLabel("Recents")
        rec_title.setObjectName("section")
        rec_head.addWidget(rec_title)
        rec_head.addStretch(1)
        self.transcript_source = QLabel("idle")
        self.transcript_source.setObjectName("card_sub")
        rec_head.addWidget(self.transcript_source)
        sl.addLayout(rec_head)

        # Compacte stat-strip (status / duur / urgentie / confidence)
        stats = QHBoxLayout()
        stats.setSpacing(10)
        self.stat_state = StatCard("Status", "Idle")
        self.stat_duration = StatCard("Duur", "00:00")
        self.stat_urgentie = StatCard("Urgentie", "0", NEG)
        self.stat_confidence = StatCard("Confidence", "0%")
        for s in (self.stat_state, self.stat_duration, self.stat_urgentie, self.stat_confidence):
            stats.addWidget(s)
        sl.addLayout(stats)

        # Live transcript (recents-stijl regels)
        self.transcript_list = QListWidget()
        self.transcript_list.setFrameShape(QFrame.Shape.NoFrame)
        self.transcript_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.transcript_list.setWordWrap(True)
        self.transcript_list.setTextElideMode(Qt.TextElideMode.ElideNone)
        sl.addWidget(self.transcript_list, 1)

        self.partial_label = QLabel("")
        self.partial_label.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 13px; font-style: italic; padding: 4px 4px;"
        )
        self.partial_label.setWordWrap(True)
        sl.addWidget(self.partial_label)

        # Alarmen + sentiment onderaan sidebar
        al_head = QHBoxLayout()
        al_title = QLabel("Actieve alarmen")
        al_title.setObjectName("card_title")
        al_head.addWidget(al_title)
        al_head.addStretch(1)
        al_meta = QLabel("urgentie & medicatie")
        al_meta.setObjectName("card_sub")
        al_head.addWidget(al_meta)
        sl.addLayout(al_head)
        self.alarm_list = QListWidget()
        self.alarm_list.setFrameShape(QFrame.Shape.NoFrame)
        self.alarm_list.setMaximumHeight(120)
        sl.addWidget(self.alarm_list)
        self.sentiment_bar = SentimentBar()
        sl.addWidget(self.sentiment_bar)

        split.addWidget(sidebar, 3)

        # RECHTS, grote gradient contactkaart
        self.contact = GradientContactCard()
        self.contact.btn_message.setIcon(qicon("user", ACCENT))
        self.contact.btn_message.setIconSize(icon_size(18))
        self.contact.btn_phone.setIcon(qicon("phone", POS))
        self.contact.btn_phone.setIconSize(icon_size(18))
        self.contact.btn_video.setIcon(qicon("headset", ACCENT))
        self.contact.btn_video.setIconSize(icon_size(18))
        self.contact.btn_mail.setIcon(qicon("phone_down", NEG))
        self.contact.btn_mail.setIconSize(icon_size(18))
        # Telefoon-knop = opnemen, ophang-knop = beëindigen.
        self.accept_btn = self.contact.btn_phone
        self.end_btn = self.contact.btn_mail
        self.accept_btn.clicked.connect(self._on_accept)
        self.end_btn.clicked.connect(self._on_end)
        self.accept_btn.setEnabled(False)
        self.end_btn.setEnabled(False)
        split.addWidget(self.contact, 2)

        root.addLayout(split, 1)

        # Gespreksgeschiedenis verhuist naar de stat-strip via history_meta;
        # we tonen de lijst onder de tegelrij niet meer apart, maar houden
        # history_list/history_meta in stand voor de poller.
        self.history_list = QListWidget()
        self.history_list.setVisible(False)
        self.history_meta = QLabel("0 gesprekken")
        self.history_meta.setVisible(False)

    def _rebuild_tiles(self, callers: list[str]) -> None:
        """Vul de avatar-tegelrij met (recente) bellers; placeholders indien leeg."""
        # Verwijder bestaande tegels (alles behalve de eind-stretch).
        while self.tiles_row.count() > 1:
            item = self.tiles_row.takeAt(0)
            if item is None:
                break
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)  # synchroon weg, geen ghost-frame
                w.deleteLater()
        names = callers[:5] or ["Beller", "Centrale", "Arts", "Mantelzorg"]
        for i, name in enumerate(names):
            self.tiles_row.insertWidget(i, AvatarTile(name))

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
        new_call_id = st.get("call_id", 0)
        if new_phase != self.phase or new_call_id != self._current_call_id:
            self._current_call_id = new_call_id
            self._phase_change(new_phase, st.get("caller", ""))
        events = st.get("events", [])
        if len(events) > self._last_event_count and self.phase == "active":
            for ev in events[self._last_event_count:]:
                self._render_transcript_line(ev.get("text", ""))
            self._last_event_count = len(events)
            self._refresh_stats()
        # Partial-line update
        partial = st.get("partial", "") if self.phase == "active" else ""
        self.partial_label.setText(("… " + partial) if partial else "")

    def _poll_history(self) -> None:
        try:
            r = requests.get(f"{self.api_url}/call/history", timeout=0.8)
            if not r.ok:
                return
            data = r.json()
        except requests.RequestException:
            return
        calls = data.get("calls", [])
        self.history_meta.setText(f"{len(calls)} gesprekken")
        # Avatar-tegelrij voeden met recente bellers (uniek, behoud volgorde).
        recent_callers: list[str] = []
        for c in calls:
            name = c.get("caller", "") or "Beller"
            if name not in recent_callers:
                recent_callers.append(name)
        self._rebuild_tiles(recent_callers)
        # Hidden history_list behouden voor eventuele export.
        self.history_list.clear()
        for c in calls:
            started = datetime.fromtimestamp(c.get("started_at", 0)).strftime("%H:%M") if c.get("started_at") else "--:--"
            n_events = len(c.get("events", []))
            line = f"  #{c.get('call_id'):>2}   {started}   {c.get('caller','')}   {c.get('duration_s',0):.0f}s   {n_events} regels"
            self.history_list.addItem(QListWidgetItem(line))

    def _phase_change(self, new_phase: str, caller: str) -> None:
        self.phase = new_phase
        if new_phase == "ringing":
            self.caller_name = caller or "Onbekende beller"
            self.contact.set_contact(self.caller_name, "RINGING · neem op", "#ff375f")
            self.contact.set_info("ringing", "-", "wacht op opnemen")
            self.accept_btn.setEnabled(True)
            self.end_btn.setEnabled(True)
            self.phase_pill.setText("BELLEN")
            self.phase_pill.setObjectName("pill_ring")
            self.stat_state.set_value("Ringing")
            self.transcript_source.setText("wacht op opnemen")
        elif new_phase == "active":
            self.contact.set_contact(self.caller_name or "Beller", "verbonden", "#34c759")
            self.contact.set_info("actief", "verbonden", "Vosk-NL live")
            self.accept_btn.setEnabled(False)
            self.end_btn.setEnabled(True)
            self.phase_pill.setText("LIVE")
            self.phase_pill.setObjectName("pill_active")
            self.stat_state.set_value("Actief")
            self.timer_seconds = 0
            self.alarm_list.clear()
            self.urgentie_count = 0
            self.pos_count = 0
            self.neg_count = 0
            self._last_event_count = 0
            # Call-separator i.p.v. transcript clearen: oude calls blijven zichtbaar
            if self.transcript_list.count() > 0:
                sep = QListWidgetItem(
                    f"  ─────  CALL #{self._current_call_id} · {datetime.now().strftime('%H:%M:%S')}  ─────"
                )
                sep.setForeground(QColor(TEXT_DIM))
                self.transcript_list.addItem(sep)
            else:
                hdr = QListWidgetItem(
                    f"  CALL #{self._current_call_id} · {datetime.now().strftime('%H:%M:%S')}"
                )
                hdr.setForeground(QColor(TEXT_DIM))
                self.transcript_list.addItem(hdr)
            self._start_audio_if_needed()
        else:  # idle
            self.caller_name = ""
            self.contact.set_contact("geen oproep", "wacht op binnenkomende oproep", "#bf5af2")
            self.contact.set_info("idle", "-", "-")
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
        line_id = len(self.transcript_history) + 1
        row = {"id": line_id, "text": text, "sentiment": sentiment,
               "confidence": confidence, "keywords": kws,
               "time": datetime.now().strftime("%H:%M:%S")}
        self.transcript_history.append(row)
        if sentiment == "positief":
            self.pos_count += 1
        elif sentiment == "negatief":
            self.neg_count += 1

        # Alle woorden in witte tekst, ID voorop, keywords als subtiele tag rechts.
        kw_tag = "  ".join(k["text"] for k in kws[:3])
        line = f"  #{line_id:>3}   {row['time']}    {text}"
        if kw_tag:
            line += f"     · {kw_tag}"
        item = QListWidgetItem(line)
        item.setForeground(QColor(TEXT))  # donkere tekst op licht thema
        self.transcript_list.addItem(item)
        self.transcript_list.scrollToBottom()

        # Alarmen: urgentie rood, medicatie oranje (licht thema).
        for kw in kws:
            if kw["type"] == "urgentie":
                self.urgentie_count += 1
                a = QListWidgetItem(
                    f"  #{self.urgentie_count:>2}   {kw['text'].upper()}       {row['time']}"
                )
                a.setForeground(QColor(NEG))
                self.alarm_list.addItem(a)
            elif kw["type"] == "medicatie":
                a = QListWidgetItem(
                    f"  #-    {kw['text']}       {row['time']}"
                )
                a.setForeground(QColor(WARN))
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

    def _on_local_partial(self, text: str) -> None:
        if self.phase != "active":
            return
        try:
            requests.post(f"{self.api_url}/call/partial",
                          json={"text": text}, timeout=0.5)
        except requests.RequestException:
            pass


class CallerScreen(QWidget):
    """Caller-scherm: call-knop + live transcript-view zodat beller ziet wat operator hoort."""

    def __init__(self, api_url: str) -> None:
        super().__init__()
        self.setWindowTitle("VitaCall")
        self.resize(420, 820)
        self.setObjectName("mobile")
        self.api_url = api_url.rstrip("/")
        self.phase = "idle"
        self.timer_seconds = 0
        self._last_event_count = 0
        self._build_ui()
        QTimer(self, timeout=self._tick, interval=1000).start()  # type: ignore[call-arg]
        QTimer(self, timeout=self._poll_state, interval=400).start()  # type: ignore[call-arg]

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 44, 28, 32)
        root.setSpacing(0)

        self.top_label = QLabel("alarmcentrale")
        self.top_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 14px;")
        self.top_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.top_label)

        root.addSpacing(4)

        self.caller_label = QLabel("VitaCall")
        self.caller_label.setStyleSheet(
            f"color: {TEXT}; font-size: 34px; font-weight: 700; letter-spacing: -1px;"
        )
        self.caller_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.caller_label)

        self.status_label = QLabel("klaar om te bellen")
        self.status_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 13px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.status_label)

        root.addSpacing(18)

        # Transcript-view (alleen zichtbaar tijdens gesprek)
        self.transcript_card = QFrame()
        self.transcript_card.setObjectName("card")
        tl = QVBoxLayout(self.transcript_card)
        tl.setContentsMargins(14, 12, 14, 12)
        tl.setSpacing(6)
        tt = QLabel("Live transcript")
        tt.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; "
                         "font-weight: 700; letter-spacing: 0.8px;")
        tl.addWidget(tt)
        self.transcript_list = QListWidget()
        self.transcript_list.setFrameShape(QFrame.Shape.NoFrame)
        self.transcript_list.setStyleSheet(f"color: {TEXT}; font-size: 12px;")
        tl.addWidget(self.transcript_list, 1)
        self.partial_label = QLabel("")
        self.partial_label.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 12px; "
            "font-style: italic; padding: 4px 2px;"
        )
        self.partial_label.setWordWrap(True)
        tl.addWidget(self.partial_label)
        self.transcript_card.setVisible(False)
        root.addWidget(self.transcript_card, 1)

        # In idle: vul met stretch
        self._stretch_above = root.addStretch(1)  # type: ignore[func-returns-value]

        # Call-knop
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
        self.call_caption.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 13px; font-weight: 500;"
        )
        self.call_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addSpacing(10)
        root.addWidget(self.call_caption)

        root.addSpacing(8)

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
            self._last_event_count = 0
            if new_phase == "ringing":
                self.status_label.setText("aan het bellen...")
                self.call_btn.setObjectName("mob_decline")
                self.call_btn.setIcon(qicon("phone_down", "white"))
                self.call_caption.setText("Ophangen")
                self.transcript_card.setVisible(False)
                self.transcript_list.clear()
            elif new_phase == "active":
                self.status_label.setText("verbonden")
                self.call_btn.setObjectName("mob_decline")
                self.call_btn.setIcon(qicon("phone_down", "white"))
                self.call_caption.setText("Ophangen")
                self.transcript_card.setVisible(True)
                self.transcript_list.clear()
            else:
                self.status_label.setText("klaar om te bellen")
                self.call_btn.setObjectName("mob_accept")
                self.call_btn.setIcon(qicon("phone", "white"))
                self.call_caption.setText("Bel alarmcentrale")
                self.transcript_card.setVisible(False)
                self.partial_label.setText("")
            self.call_btn.style().unpolish(self.call_btn)
            self.call_btn.style().polish(self.call_btn)

        if self.phase == "active":
            events = st.get("events", [])
            if len(events) > self._last_event_count:
                for ev in events[self._last_event_count:]:
                    txt = ev.get("text", "")
                    line_id = self._last_event_count + 1
                    item = QListWidgetItem(f"  #{line_id:>3}  {txt}")
                    item.setForeground(QColor(TEXT))
                    self.transcript_list.addItem(item)
                    self._last_event_count += 1
                self.transcript_list.scrollToBottom()
            partial = st.get("partial", "")
            self.partial_label.setText(("… " + partial) if partial else "")

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
