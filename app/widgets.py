"""Gedeelde Qt-widgets en stylesheet."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

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
QFrame.metric_box { background: #1c1c1e; border: 1px solid rgba(255,255,255,0.07); border-radius: 8px; }
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
        self._progress = min((time.time() - self._start_t) / 2.0, 1.0)
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
        p.drawArc(self.rect().adjusted(2, 2, -2, -2), 90 * 16, -int(360 * 16 * self._progress))
