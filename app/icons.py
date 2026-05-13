"""Font-Awesome iconen via qtawesome."""
from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon

import qtawesome as qta

# Mapping van semantische naam → Font Awesome icon-id.
_ICONS = {
    "phone": "fa5s.phone",
    "phone_down": "fa5s.phone-slash",
    "mic": "fa5s.microphone",
    "mic_off": "fa5s.microphone-slash",
    "alert": "fa5s.exclamation-triangle",
    "pill": "fa5s.pills",
    "export": "fa5s.file-export",
    "dot": "fa5s.circle",
    "user": "fa5s.user",
    "headset": "fa5s.headset",
    "wave": "fa5s.signal",
    "check": "fa5s.check",
    "x": "fa5s.times",
}


def qicon(kind: str, color: str = "white") -> QIcon:
    return qta.icon(_ICONS.get(kind, "fa5s.question"), color=color)


def icon_size(px: int) -> QSize:
    return QSize(px, px)
