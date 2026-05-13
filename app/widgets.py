"""Flat moderne Qt-widgets en stylesheet voor VitaCall."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

# Palet (flat, geen gradients).
BG_LIGHT = "#f4f5f7"      # operator-achtergrond
BG_CARD = "#ffffff"       # cards in operator
BG_DARK = "#101012"       # mobile-achtergrond
TEXT = "#0a0a0c"
TEXT_DIM = "#6b6b73"
TEXT_INV = "#f5f5f7"
ACCENT = "#ff8a00"        # oranje, zoals foto 3
ACCENT_BG = "#fff1de"
POS = "#10b981"
NEG = "#ef4444"
WARN = "#f59e0b"

STYLE = f"""
* {{ font-family: 'Inter', 'Segoe UI Variable', 'Segoe UI', sans-serif; color: {TEXT}; }}

/* Operator dashboard - light theme */
QWidget#shell {{ background: {BG_LIGHT}; }}
QWidget#topbar {{ background: {BG_LIGHT}; }}
QFrame#card {{
    background: {BG_CARD};
    border-radius: 16px;
    border: 1px solid #e5e7eb;
}}
QFrame#card_dark {{
    background: #0a0a0c;
    border-radius: 16px;
}}
QFrame#card_alarm {{
    background: {ACCENT_BG};
    border-radius: 16px;
    border: 1px solid #fed7aa;
}}
QLabel#page_title {{ font-size: 24px; font-weight: 700; color: {TEXT}; letter-spacing: -0.5px; }}
QLabel#card_title {{ font-size: 16px; font-weight: 700; color: {TEXT}; letter-spacing: -0.2px; }}
QLabel#card_sub   {{ font-size: 12px; color: {TEXT_DIM}; }}
QLabel#big_value  {{ font-size: 32px; font-weight: 700; color: {TEXT}; letter-spacing: -1px; }}
QLabel#stat_label {{ font-size: 11px; color: {TEXT_DIM}; font-weight: 600; letter-spacing: 0.3px; }}
QLabel#stat_value {{ font-size: 22px; font-weight: 700; color: {TEXT}; letter-spacing: -0.5px; }}
QLabel#pill_active {{
    background: {ACCENT}; color: white;
    font-size: 11px; padding: 4px 12px; border-radius: 12px; font-weight: 700;
}}
QLabel#pill_ok {{
    background: #d1fae5; color: {POS};
    font-size: 11px; padding: 4px 10px; border-radius: 10px; font-weight: 700;
}}
QLabel#pill_off {{
    background: #f3f4f6; color: {TEXT_DIM};
    font-size: 11px; padding: 4px 10px; border-radius: 10px; font-weight: 700;
}}
QPushButton#cta_dark {{
    background: #0a0a0c; color: white;
    border-radius: 22px; padding: 10px 22px; font-weight: 700; font-size: 13px;
}}
QPushButton#cta_dark:hover {{ background: #2a2a2c; }}
QPushButton#cta_accent {{
    background: {ACCENT}; color: white;
    border-radius: 22px; padding: 10px 22px; font-weight: 700; font-size: 13px;
}}

QFrame#alarm_row {{ background: white; border-radius: 12px; border: 1px solid #f1f2f4; }}
QLabel.alarm_title {{ font-size: 14px; font-weight: 700; color: {NEG}; }}
QLabel.alarm_title_warn {{ font-size: 14px; font-weight: 700; color: {WARN}; }}
QLabel.alarm_meta {{ font-size: 11px; color: {TEXT_DIM}; }}

/* Mobile - dark call-screen */
QWidget#mobile {{ background: {BG_DARK}; }}
QLabel.mob_caller  {{ color: white; font-size: 36px; font-weight: 600; letter-spacing: -1px; }}
QLabel.mob_label   {{ color: rgba(255,255,255,0.55); font-size: 15px; font-weight: 500; }}
QLabel.mob_status  {{ color: rgba(255,255,255,0.4); font-size: 13px; }}
QLabel.mob_subtitle {{ color: rgba(255,255,255,0.9); font-size: 17px; font-weight: 500; }}

QPushButton#mob_accept {{
    background: {POS}; border-radius: 36px;
    min-width: 72px; min-height: 72px; max-width: 72px; max-height: 72px;
    font-size: 28px; color: white;
}}
QPushButton#mob_decline {{
    background: {NEG}; border-radius: 36px;
    min-width: 72px; min-height: 72px; max-width: 72px; max-height: 72px;
    font-size: 28px; color: white;
}}
QPushButton#mob_action {{
    background: rgba(255,255,255,0.12); border-radius: 28px;
    min-width: 56px; min-height: 56px; max-width: 56px; max-height: 56px;
    color: white; font-size: 18px;
}}
QPushButton#mob_action:hover {{ background: rgba(255,255,255,0.18); }}

QScrollArea, QListWidget {{ background: transparent; border: 0; }}
QScrollBar:vertical {{ background: transparent; width: 6px; }}
QScrollBar::handle:vertical {{ background: rgba(0,0,0,0.15); border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""


class IconButton(QPushButton):
    """Ronde knop met een unicode-symbool als icon."""

    def __init__(self, symbol: str, object_name: str) -> None:
        super().__init__(symbol)
        self.setObjectName(object_name)
        f = self.font()
        f.setFamily("Segoe UI Emoji")
        self.setFont(f)


class StatCard(QFrame):
    """Compacte witte stat-card met label + waarde."""

    def __init__(self, label: str, value: str, color: str | None = None) -> None:
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        lbl = QLabel(label.upper())
        lbl.setObjectName("stat_label")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("stat_value")
        if color:
            self.value_label.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: 700;")
        layout.addWidget(lbl)
        layout.addWidget(self.value_label)

    def set_value(self, text: str) -> None:
        self.value_label.setText(text)


class SentimentBar(QWidget):
    """Horizontale stacked bar: groen positief vs rood negatief."""

    def __init__(self) -> None:
        super().__init__()
        self.fraction = 0.5
        self.setFixedHeight(10)

    def set_pos(self, fraction: float) -> None:
        self.fraction = max(0.0, min(1.0, fraction))
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#e5e7eb"))
        p.drawRoundedRect(0, 0, w, h, h / 2, h / 2)
        if w <= 0:
            return
        pos_w = int(w * self.fraction)
        if pos_w > 0:
            p.setBrush(QColor(POS))
            p.drawRoundedRect(0, 0, pos_w, h, h / 2, h / 2)
        if pos_w < w:
            p.setBrush(QColor(NEG))
            p.drawRoundedRect(pos_w, 0, w - pos_w, h, h / 2, h / 2)


class PulseDot(QWidget):
    """Rode pulserende dot voor 'recording'."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(14, 14)
        self._phase = 0.0
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(60)

    def _tick(self) -> None:
        self._phase = (self._phase + 0.08) % 6.28
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        alpha = int(180 + 60 * math.sin(self._phase))
        p.setBrush(QColor(239, 68, 68, alpha))
        p.drawEllipse(2, 2, 10, 10)
