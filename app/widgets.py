"""Gedeelde Qt-widgets en stylesheet."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

STYLE = """
* { font-family: 'Inter', 'Segoe UI Variable', 'Segoe UI', sans-serif; color: #f5f5f7; }
QWidget#shell  { background: #0a0a0c; }
QWidget#admin  { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                  stop:0 #0d0d10, stop:1 #08080a);
                 border-right: 1px solid rgba(255,255,255,0.06); }
QWidget#call   { background: #0a0a0c; }
QWidget#mobile { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                  stop:0 #0d0d10, stop:1 #050507); }
QLabel#brand   { font-size: 15px; font-weight: 800; color: #fff; letter-spacing: -0.3px; }
QLabel#caller_name { font-size: 46px; font-weight: 700; letter-spacing: -1.2px; color: #fff; }
QLabel#caller_sub  { color: rgba(255,255,255,0.55); font-size: 15px; font-weight: 500; }
QLabel#section_title {
    font-size: 10px; font-weight: 800; letter-spacing: 1.4px;
    color: rgba(255,255,255,0.4); text-transform: uppercase;
}
QLabel.dim   { color: rgba(255,255,255,0.35); font-style: italic; font-size: 12px; }
QLabel.empty { color: rgba(255,255,255,0.3); font-style: italic; font-size: 12px; }
QLabel.pos   { color: #30d158; font-weight: 700; }
QLabel.neg   { color: #ff453a; font-weight: 700; }
QLabel.amb   { color: #ffd60a; font-weight: 700; }
QLabel.metric_label { font-size: 9px; color: rgba(255,255,255,0.4); letter-spacing: 0.8px; font-weight: 700; }
QFrame.metric_box {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 #1a1a1c, stop:1 #141416);
    border: 1px solid rgba(255,255,255,0.06); border-radius: 12px;
}
QLabel#pill_on  { background: rgba(48,209,88,0.18); color: #30d158;
                   font-size: 10px; padding: 3px 10px; border-radius: 10px; font-weight: 800;
                   border: 1px solid rgba(48,209,88,0.3); }
QLabel#pill_off { background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.45);
                   font-size: 10px; padding: 3px 10px; border-radius: 10px; font-weight: 700;
                   border: 1px solid rgba(255,255,255,0.08); }
QFrame#row_pos {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 rgba(48,209,88,0.12), stop:1 rgba(48,209,88,0.04));
    border-left: 3px solid #30d158; border-radius: 12px;
}
QFrame#row_neg {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 rgba(255,69,58,0.13), stop:1 rgba(255,69,58,0.04));
    border-left: 3px solid #ff453a; border-radius: 12px;
}
QFrame#row     { background: #1a1a1c; border-left: 3px solid rgba(255,255,255,0.2); border-radius: 12px; }
QPushButton#accept {
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.6, fx:0.5, fy:0.5,
                stop:0 #34d870, stop:1 #1fa951);
    border-radius: 36px; min-width: 72px; min-height: 72px;
    max-width: 72px; max-height: 72px; font-weight: 800; font-size: 26px; color: #fff;
    border: 1px solid rgba(255,255,255,0.15);
}
QPushButton#accept:hover { background: #38e078; }
QPushButton#decline, QPushButton#endcall {
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.6, fx:0.5, fy:0.5,
                stop:0 #ff5547, stop:1 #d92e23);
    border-radius: 36px; min-width: 72px; min-height: 72px;
    max-width: 72px; max-height: 72px; font-weight: 800; font-size: 26px; color: #fff;
    border: 1px solid rgba(255,255,255,0.15);
}
QPushButton#decline:hover, QPushButton#endcall:hover { background: #ff6357; }
QPushButton#mob_call {
    background: qradialgradient(cx:0.5, cy:0.4, radius:0.7, fx:0.5, fy:0.4,
                stop:0 #34d870, stop:1 #1fa951);
    border-radius: 44px; min-width: 88px; min-height: 88px;
    max-width: 88px; max-height: 88px; font-size: 30px; font-weight: 800; color: #fff;
    border: 1px solid rgba(255,255,255,0.18);
}
QPushButton#mob_end {
    background: qradialgradient(cx:0.5, cy:0.4, radius:0.7, fx:0.5, fy:0.4,
                stop:0 #ff5547, stop:1 #d92e23);
    border-radius: 44px; min-width: 88px; min-height: 88px;
    max-width: 88px; max-height: 88px; font-size: 26px; font-weight: 800; color: #fff;
    border: 1px solid rgba(255,255,255,0.18);
}
QLineEdit {
    background: #18181a; padding: 10px 14px; border-radius: 10px;
    border: 1px solid rgba(255,255,255,0.08); font-size: 13px; color: #f5f5f7;
}
QLineEdit:focus { border: 1px solid rgba(48,209,88,0.5); }
QScrollArea, QListWidget { background: transparent; border: 0; }
QListWidget::item { padding: 10px 12px; border-radius: 8px; font-size: 13px; margin: 2px 0; }
QListWidget::item:hover { background: rgba(255,255,255,0.05); }
QListWidget::item:selected { background: rgba(48,209,88,0.12); }
QScrollBar:vertical { background: transparent; width: 6px; }
QScrollBar::handle:vertical { background: rgba(255,255,255,0.15); border-radius: 3px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: rgba(255,255,255,0.25); }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
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
        p.setBrush(QColor("#2a2a2c"))
        p.drawRoundedRect(0, 0, w, h, h / 2, h / 2)
        if w <= 0:
            return
        pos_w = int(w * self.fraction)
        if pos_w > 0:
            p.setBrush(QColor("#30d158"))
            p.drawRoundedRect(0, 0, pos_w, h, h / 2, h / 2)
        if pos_w < w:
            p.setBrush(QColor("#ff453a"))
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
