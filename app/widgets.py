"""Flat moderne Qt-widgets en stylesheet voor VitaCall."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

# Palet — pure dark mode, geen gradients.
BG_DARK = "#0a0a0c"        # achtergrond beide vensters
BG_CARD = "#16161a"        # cards
BG_CARD_HI = "#1c1c20"     # subtiel verhoogd
BORDER = "#26262b"
TEXT = "#f5f5f7"
TEXT_DIM = "#8b8b94"
ACCENT = "#ff8a00"         # oranje accent
ACCENT_DIM = "#3a2410"
POS = "#10b981"
POS_DIM = "#0b3127"
NEG = "#ef4444"
NEG_DIM = "#3a1414"
WARN = "#f59e0b"

STYLE = f"""
* {{ font-family: 'Inter', 'Segoe UI Variable', 'Segoe UI', sans-serif; color: {TEXT}; }}

QWidget#shell {{ background: {BG_DARK}; }}
QFrame#card {{
    background: {BG_CARD};
    border-radius: 16px;
    border: 1px solid {BORDER};
}}
QFrame#card_hi {{
    background: {BG_CARD_HI};
    border-radius: 16px;
    border: 1px solid {BORDER};
}}
QFrame#card_alarm {{
    background: {ACCENT_DIM};
    border-radius: 16px;
    border: 1px solid {ACCENT};
}}
QLabel#page_title {{ font-size: 26px; font-weight: 700; color: {TEXT}; letter-spacing: -0.5px; }}
QLabel#page_sub   {{ font-size: 13px; color: {TEXT_DIM}; }}
QLabel#card_title {{ font-size: 16px; font-weight: 700; color: {TEXT}; letter-spacing: -0.2px; }}
QLabel#card_sub   {{ font-size: 12px; color: {TEXT_DIM}; }}
QLabel#big_value  {{ font-size: 32px; font-weight: 700; color: {TEXT}; letter-spacing: -1px; }}
QLabel#stat_label {{ font-size: 10px; color: {TEXT_DIM}; font-weight: 700; letter-spacing: 0.8px; }}
QLabel#stat_value {{ font-size: 24px; font-weight: 700; color: {TEXT}; letter-spacing: -0.5px; }}
QLabel#pill_active {{
    background: {ACCENT}; color: #0a0a0c;
    font-size: 11px; padding: 4px 12px; border-radius: 12px; font-weight: 800;
}}
QLabel#pill_ok {{
    background: {POS_DIM}; color: {POS};
    font-size: 11px; padding: 4px 10px; border-radius: 10px; font-weight: 700;
    border: 1px solid {POS};
}}
QLabel#pill_off {{
    background: {BG_CARD_HI}; color: {TEXT_DIM};
    font-size: 11px; padding: 4px 10px; border-radius: 10px; font-weight: 700;
    border: 1px solid {BORDER};
}}
QPushButton#cta_dark {{
    background: {BG_CARD_HI}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 22px;
    padding: 10px 22px; font-weight: 700; font-size: 13px;
}}
QPushButton#cta_dark:hover {{ background: {BORDER}; }}
QPushButton#cta_accent {{
    background: {ACCENT}; color: #0a0a0c;
    border-radius: 22px; padding: 10px 22px; font-weight: 800; font-size: 13px;
}}
QPushButton#cta_accent:hover {{ background: #ffa033; }}

QLabel.alarm_title      {{ font-size: 14px; font-weight: 700; color: {NEG}; }}
QLabel.alarm_title_warn {{ font-size: 14px; font-weight: 700; color: {WARN}; }}
QLabel.alarm_meta       {{ font-size: 11px; color: {TEXT_DIM}; }}

/* Mobile - call-screen */
QWidget#mobile {{ background: {BG_DARK}; }}
QPushButton#mob_accept {{
    background: {POS}; border-radius: 38px;
    min-width: 76px; min-height: 76px; max-width: 76px; max-height: 76px;
    font-size: 30px; color: white;
}}
QPushButton#mob_decline {{
    background: {NEG}; border-radius: 38px;
    min-width: 76px; min-height: 76px; max-width: 76px; max-height: 76px;
    font-size: 30px; color: white;
}}
QPushButton#mob_action {{
    background: rgba(255,255,255,0.10); border-radius: 30px;
    min-width: 60px; min-height: 60px; max-width: 60px; max-height: 60px;
    color: white; font-size: 20px;
}}
QPushButton#mob_action:hover {{ background: rgba(255,255,255,0.16); }}

QScrollArea, QListWidget {{ background: transparent; border: 0; color: {TEXT}; }}
QListWidget {{ font-size: 13px; }}
QListWidget::item {{ padding: 8px 10px; border-radius: 6px; }}
QListWidget::item:hover {{ background: rgba(255,255,255,0.04); }}
QScrollBar:vertical {{ background: transparent; width: 6px; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.12); border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.22); }}
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
        p.setBrush(QColor("#2a2a2f"))
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
