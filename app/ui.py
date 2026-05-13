"""VitaCall desktop UI — operator + beller vensters.

    python app/ui.py              # operator (alarmcentrale) + embedded backend
    python app/ui.py --mobile     # beller
    python app/ui.py --no-server  # operator zonder backend (extern uvicorn)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Maak `from app.*` ook werken als script-mode (python app/ui.py) wordt gebruikt.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from PySide6.QtCore import Qt, QTimer, Signal
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
    QVBoxLayout,
    QWidget,
)

from app.backend import start_api_server
from app.models import EdgeModel, api_health, find_keywords, score_text
from app.signals import AudioBridge, FileBus
from app.widgets import HoldButton, STYLE, StackedBar, make_metric_box

ROOT = Path(__file__).resolve().parent.parent
LITE_MODEL_PATH = ROOT / "models" / "sentiment_lite.json"
HEAVY_MODEL_PATH = ROOT / "models" / "sentiment_heavy.pkl"
SIGNAL_FILE = ROOT / "signaling.json"
VOSK_DIR = ROOT / "models" / "vosk-nl"


# ====== Operator window ======
class OperatorWindow(QWidget):
    def __init__(self, edge_model: EdgeModel | None) -> None:
        super().__init__()
        self.setWindowTitle("VitaCall — alarmcentrale")
        self.resize(1100, 720)
        self.setObjectName("shell")
        self.edge_model = edge_model
        self.bus = FileBus("operator", SIGNAL_FILE)
        self.bus.message.connect(self._on_message)
        self.audio = AudioBridge(VOSK_DIR)
        self.state = "idle"
        self.caller_id = ""
        self.caller_name = ""
        self.timer_seconds = 0
        self.transcript: list[dict] = []
        self.keywords: list[dict] = []
        self.history: list[dict] = []
        self._build_ui()
        QTimer(self, timeout=self._on_tick, interval=1000).start()  # type: ignore[call-arg]
        t = QTimer(self, timeout=self._refresh_health, interval=3000)  # type: ignore[call-arg]
        t.start()
        self._refresh_health()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        admin = QWidget()
        admin.setObjectName("admin")
        admin.setFixedWidth(210)
        a = QVBoxLayout(admin)
        a.setContentsMargins(16, 22, 16, 22)
        a.setSpacing(14)

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

        a.addSpacing(8)
        a.addWidget(self._section_title("Handmatig fragment"))
        self.manual = QLineEdit()
        self.manual.setPlaceholderText("type wat de beller zegt en druk enter")
        self.manual.returnPressed.connect(self._submit_manual)
        a.addWidget(self.manual)
        a.addStretch(1)

        # Center
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

        self.transcript_area = QScrollArea()
        self.transcript_area.setWidgetResizable(True)
        self.transcript_inner = QWidget()
        self.transcript_layout = QVBoxLayout(self.transcript_inner)
        self.transcript_layout.setSpacing(10)
        self.transcript_layout.addStretch(1)
        self.transcript_area.setWidget(self.transcript_inner)
        c.addWidget(self.transcript_area, 1)

        self.queue = QListWidget()
        self.queue.itemClicked.connect(self._open_history_item)
        self.queue.setMaximumHeight(180)
        c.addWidget(self.queue)

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
        for w in (self.btn_decline, self.btn_accept, self.btn_end, self.idle_lbl):
            actions.addWidget(w)
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
        self.pill.setText("verbonden" if up else "offline")
        self.pill.setObjectName("pill_on" if up else "pill_off")
        self.pill.setStyleSheet("")

    def _refresh_state(self) -> None:
        live = self.state == "live"
        incoming = self.state == "incoming"
        idle = self.state == "idle"

        if idle:
            self.caller_lbl.setText("Geen actieve oproep")
            last = self.history[0] if self.history else None
            self.caller_sub.setText(f"laatste oproep {last['time']}" if last else "systeem klaar, geen actieve melding")
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

        n = len(self.transcript)
        pos = sum(1 for t in self.transcript if t.get("sentiment") == "positief")
        pos_pct = round(pos / n * 100) if n else 0
        avg_conf = round(sum(t.get("confidence", 0) for t in self.transcript) / n * 100) if n else 0
        self.bar.set_pos(pos / n if n else 0.0)
        self.box_pos._value_label.setText(f"{pos_pct}%")  # type: ignore[attr-defined]
        self.box_neg._value_label.setText(f"{100 - pos_pct if n else 0}%")  # type: ignore[attr-defined]
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

        is_urgent = any(k["type"] == "urgentie" for k in self.keywords)
        self.setProperty("class", "urgent" if is_urgent else "")
        self.style().unpolish(self)
        self.style().polish(self)

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
                self.kw_list.addItem(QListWidgetItem(f"●  {k['text']}   {k['type']}"))
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
        if h:
            HistoryDialog(h, self).exec()


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
        close.setStyleSheet("background: #2c2c2e; padding: 10px 18px; border-radius: 10px; font-weight: 600;")
        v.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)


# ====== Beller (mobile) ======
class MobileWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VitaCall — beller")
        self.resize(420, 720)
        self.setObjectName("mobile")
        self.bus = FileBus("caller", SIGNAL_FILE)
        self.bus.message.connect(self._on_message)
        self.audio = AudioBridge(VOSK_DIR)
        self.state = "idle"
        self.timer_seconds = 0
        self._build_ui()
        QTimer(self, timeout=self._on_tick, interval=1000).start()  # type: ignore[call-arg]

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 40, 28, 40)
        root.setSpacing(0)

        top_lbl = QLabel("VitaCall")
        top_lbl.setObjectName("brand")
        sub_lbl = QLabel("alarmcentrale")
        sub_lbl.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 12px;")
        root.addWidget(top_lbl)
        root.addWidget(sub_lbl)
        root.addSpacing(32)

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

        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("typ wat je zegt en druk enter")
        self.text_input.returnPressed.connect(self._send_text)
        self.text_input.hide()
        root.addWidget(self.text_input)
        root.addSpacing(16)

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
    p.add_argument("--no-server", action="store_true", help="start backend niet (extern uvicorn)")
    args = p.parse_args()

    if args.reset and SIGNAL_FILE.exists():
        SIGNAL_FILE.unlink()

    if not args.mobile and not args.no_server:
        start_api_server(HEAVY_MODEL_PATH, "http://127.0.0.1:8000")

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)

    if args.mobile:
        w: QWidget = MobileWindow()
    else:
        edge = EdgeModel.load(LITE_MODEL_PATH)
        if edge is None:
            print(f"[warn] edge-model niet gevonden op {LITE_MODEL_PATH}")
        w = OperatorWindow(edge)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
