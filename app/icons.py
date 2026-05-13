"""Vector-iconen via QPainter (geen emoji, geen externe assets)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QLabel


def _phone_path(size: int) -> QPainterPath:
    """Klassieke handset-vorm."""
    p = QPainterPath()
    s = size
    p.moveTo(s * 0.22, s * 0.32)
    p.cubicTo(s * 0.30, s * 0.20, s * 0.38, s * 0.20, s * 0.42, s * 0.30)
    p.lineTo(s * 0.36, s * 0.42)
    p.cubicTo(s * 0.42, s * 0.58, s * 0.50, s * 0.66, s * 0.64, s * 0.72)
    p.lineTo(s * 0.76, s * 0.66)
    p.cubicTo(s * 0.86, s * 0.70, s * 0.86, s * 0.78, s * 0.74, s * 0.86)
    p.cubicTo(s * 0.62, s * 0.94, s * 0.40, s * 0.86, s * 0.26, s * 0.72)
    p.cubicTo(s * 0.14, s * 0.58, s * 0.14, s * 0.40, s * 0.22, s * 0.32)
    p.closeSubpath()
    return p


def make_icon_label(kind: str, size: int = 28, color: str = "#ffffff") -> QLabel:
    """Maakt een QLabel met een gerenderd vector-icoon erin."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = QColor(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)

    if kind == "phone":
        p.drawPath(_phone_path(size))
    elif kind == "phone_down":
        # Handset gekanteld (hang-op).
        p.save()
        p.translate(size / 2, size / 2)
        p.rotate(135)
        p.translate(-size / 2, -size / 2)
        p.drawPath(_phone_path(size))
        p.restore()
    elif kind == "dot":
        p.drawEllipse(QPointF(size / 2, size / 2), size * 0.28, size * 0.28)
    elif kind == "alert":
        # Driehoek met uitroepteken
        path = QPainterPath()
        path.moveTo(size * 0.5, size * 0.12)
        path.lineTo(size * 0.92, size * 0.86)
        path.lineTo(size * 0.08, size * 0.86)
        path.closeSubpath()
        p.drawPath(path)
        p.setBrush(QColor("#0a0a0c"))
        p.drawRect(QRectF(size * 0.46, size * 0.36, size * 0.08, size * 0.30))
        p.drawEllipse(QPointF(size / 2, size * 0.76), size * 0.05, size * 0.05)
    elif kind == "pill":
        # Capsule (medicatie)
        p.drawRoundedRect(QRectF(size * 0.18, size * 0.36, size * 0.64, size * 0.28),
                          size * 0.14, size * 0.14)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawRect(QRectF(size * 0.48, size * 0.36, size * 0.04, size * 0.28))
    elif kind == "wave":
        # 3 verticale staafjes (live-mic)
        pen = QPen(c)
        pen.setWidth(max(2, size // 14))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        cx = size / 2
        for i, dy in enumerate([0.22, 0.10, 0.30]):
            x = cx + (i - 1) * size * 0.18
            p.drawLine(int(x), int(size * (0.5 - dy)), int(x), int(size * (0.5 + dy)))
    elif kind == "export":
        # Pijl omhoog uit bakje
        pen = QPen(c)
        pen.setWidth(max(2, size // 12))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(int(size * 0.5), int(size * 0.18), int(size * 0.5), int(size * 0.62))
        p.drawLine(int(size * 0.5), int(size * 0.18), int(size * 0.32), int(size * 0.36))
        p.drawLine(int(size * 0.5), int(size * 0.18), int(size * 0.68), int(size * 0.36))
        p.drawLine(int(size * 0.20), int(size * 0.74), int(size * 0.80), int(size * 0.74))
        p.drawLine(int(size * 0.20), int(size * 0.74), int(size * 0.20), int(size * 0.86))
        p.drawLine(int(size * 0.80), int(size * 0.74), int(size * 0.80), int(size * 0.86))
    p.end()

    lbl = QLabel()
    lbl.setPixmap(pix)
    lbl.setFixedSize(size, size)
    return lbl
