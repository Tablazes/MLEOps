"""macOS Tahoe 'Phone'-app look voor VitaCall, licht thema.

Esthetiek: macOS 26 (Tahoe) Phone-app. Helder venster met grote radius,
hairline-borders, avatar-tegelrij, recents-lijst links en een grote
contactkaart met magenta→roze gradient rechts plus ronde actieknoppen.
Traffic-light dots linksboven, grid + zoek rechtsboven.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Palet, macOS Tahoe "Phone", licht.
# ---------------------------------------------------------------------------
BG_DESK = "#ececef"          # bureaublad achter het venster
BG_WIN = "#ffffff"           # venster-content (helder)
BG_SIDEBAR = "#f6f6f8"       # iets koeler voor recents-kolom
BG_INSET = "#f0f0f3"         # ingezonken velden / hover
BG_TILE = "#f2f2f5"          # avatar-tegel achtergrond
BORDER = "#e2e2e6"           # hairline separator
HAIRLINE = "rgba(0,0,0,0.08)"
TEXT = "#1c1c1e"             # primair label (bijna-zwart)
TEXT_DIM = "#8a8a8e"         # secundair label
TEXT_FAINT = "#b0b0b4"       # tertiair
ACCENT = "#007aff"           # macOS system blue (light)
ACCENT_HI = "#3393ff"
POS = "#34c759"              # system green (light)
POS_DIM = "#e7f8ec"
NEG = "#ff3b30"              # system red (light)
NEG_DIM = "#ffeceb"
WARN = "#ff9500"             # system orange (light)

# Contactkaart-vulling: solide accent (geen gradient).
PANEL_FILL = "#007aff"

# Traffic lights.
TL_RED = "#ff5f57"
TL_YELLOW = "#febc2e"
TL_GREEN = "#28c840"

FONT_STACK = ("'SF Pro Display', 'SF Pro Text', '-apple-system', "
              "'Segoe UI Variable Display', 'Segoe UI', system-ui, sans-serif")

STYLE = f"""
* {{ font-family: 'SF Pro Display', 'Inter', 'Segoe UI Variable', 'Segoe UI', sans-serif; color: {TEXT}; }}

QWidget#shell {{ background: {BG_DESK}; }}

/* Het 'venster': helder, grote radius, hairline border. */
QFrame#window {{
    background: {BG_WIN};
    border-radius: 22px;
    border: 1px solid {BORDER};
}}

/* Recents/transcript-kolom links. */
QFrame#sidebar {{
    background: {BG_SIDEBAR};
    border-radius: 16px;
    border: 1px solid {BORDER};
}}
QFrame#card {{
    background: {BG_WIN};
    border-radius: 16px;
    border: 1px solid {BORDER};
}}

QLabel#page_title {{ font-size: 22px; font-weight: 800; color: {TEXT}; letter-spacing: -0.4px; }}
QLabel#section    {{ font-size: 20px; font-weight: 800; color: {TEXT}; letter-spacing: -0.3px; }}
QLabel#card_title {{ font-size: 15px; font-weight: 700; color: {TEXT}; letter-spacing: -0.2px; }}
QLabel#card_sub   {{ font-size: 12px; color: {TEXT_DIM}; }}
QLabel#tile_name  {{ font-size: 12px; color: {TEXT}; font-weight: 600; }}
QLabel#stat_label {{ font-size: 10px; color: {TEXT_DIM}; font-weight: 700; letter-spacing: 0.8px; }}
QLabel#stat_value {{ font-size: 22px; font-weight: 800; color: {TEXT}; letter-spacing: -0.5px; }}

/* Status-pills. */
QLabel#pill_active {{
    background: {POS_DIM}; color: {POS};
    font-size: 11px; padding: 4px 12px; border-radius: 11px; font-weight: 700;
}}
QLabel#pill_idle {{
    background: {BG_INSET}; color: {TEXT_DIM};
    font-size: 11px; padding: 4px 12px; border-radius: 11px; font-weight: 700;
}}
QLabel#pill_ring {{
    background: #fff2e0; color: {WARN};
    font-size: 11px; padding: 4px 12px; border-radius: 11px; font-weight: 700;
}}

/* Toolbar-knopjes (Edit / sort / grid). */
QPushButton#tool {{
    background: {BG_INSET}; color: {TEXT};
    border: 0; border-radius: 13px; padding: 6px 14px;
    font-size: 13px; font-weight: 600; min-height: 14px;
}}
QPushButton#tool:hover {{ background: {BORDER}; }}

/* Zoekveld-look (niet-interactief label). */
QLabel#search {{
    background: {BG_INSET}; color: {TEXT_DIM};
    border-radius: 13px; padding: 7px 14px; font-size: 13px;
}}

/* Primaire / rode CTA's. */
QPushButton#cta_accent {{
    background: {ACCENT}; color: white;
    border-radius: 999px; padding: 11px 26px; font-weight: 700; font-size: 13px;
    min-height: 20px;
}}
QPushButton#cta_accent:hover {{ background: {ACCENT_HI}; }}
QPushButton#cta_accent:disabled {{ background: #d7d7db; color: white; }}
QPushButton#cta_red {{
    background: {NEG}; color: white;
    border-radius: 999px; padding: 11px 26px; font-weight: 700; font-size: 13px;
    min-height: 20px;
}}
QPushButton#cta_red:hover {{ background: #ff6259; }}
QPushButton#cta_red:disabled {{ background: #d7d7db; color: white; }}

/* Lijsten (recents / transcript / history / alarmen). */
QScrollArea, QListWidget {{ background: transparent; border: 0; color: {TEXT}; }}
QListWidget {{ font-size: 13px; }}
QListWidget::item {{ padding: 9px 10px; border-radius: 10px; color: {TEXT}; }}
QListWidget::item:hover {{ background: {BG_INSET}; }}
QListWidget::item:selected {{ background: {BG_INSET}; color: {TEXT}; }}
QScrollBar:vertical {{ background: transparent; width: 7px; }}
QScrollBar::handle:vertical {{ background: rgba(0,0,0,0.16); border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(0,0,0,0.28); }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

/* --- Mobile / call-screen (licht) --- */
QWidget#mobile {{ background: {BG_WIN}; }}
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
"""


def _initials(name: str) -> str:
    parts = [p for p in name.replace("-", " ").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


class TrafficLights(QWidget):
    """Drie macOS venster-knoppen (rood/geel/groen) linksboven."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(60, 14)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        for i, c in enumerate((TL_RED, TL_YELLOW, TL_GREEN)):
            p.setBrush(QColor(c))
            p.drawEllipse(i * 20, 1, 12, 12)


class AvatarTile(QWidget):
    """Vierkante afgeronde avatar-tegel met initialen + naam eronder.

    Kleur wordt deterministisch uit de naam afgeleid, zodat dezelfde beller
    altijd dezelfde tegelkleur krijgt (zoals de gekleurde Memoji-tegels).
    """

    _PALETTE = ["#ff9f0a", "#34c759", "#5e5ce6", "#ff375f", "#0a84ff", "#bf5af2"]

    def __init__(self, name: str, sub: str = "") -> None:
        super().__init__()
        self.name = name
        self.sub = sub
        self.setFixedWidth(86)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.tile = _AvatarBox(name, self._color_for(name))
        lay.addWidget(self.tile, alignment=Qt.AlignmentFlag.AlignHCenter)

        lbl = QLabel(name.split()[0] if name else "-")
        lbl.setObjectName("tile_name")
        lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(lbl)

    def _color_for(self, name: str) -> str:
        if not name:
            return TEXT_FAINT
        idx = sum(ord(c) for c in name) % len(self._PALETTE)
        return self._PALETTE[idx]


class _AvatarBox(QWidget):
    """De gekleurde, afgeronde tegel met initialen."""

    def __init__(self, name: str, color: str) -> None:
        super().__init__()
        self.initials = _initials(name)
        self.color = color
        self.setFixedSize(74, 74)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 18, 18)
        # Solide vlakvulling (geen gradient).
        p.fillPath(path, QColor(self.color))
        p.setPen(QColor("white"))
        f = QFont(self.font())
        f.setPointSize(22)
        f.setWeight(QFont.Weight.Bold)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.initials)


class RoundActionButton(QPushButton):
    """Ronde witte actieknop met gekleurd icoon (message/phone/video/mail)."""

    def __init__(self, color: str = ACCENT) -> None:
        super().__init__()
        self.setFixedSize(44, 44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QPushButton {"
            "  background: rgba(255,255,255,0.92);"
            "  border: 0; border-radius: 22px;"
            "}"
            "QPushButton:hover { background: white; }"
            "QPushButton:disabled { background: rgba(255,255,255,0.55); }"
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(14)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 45))
        self.setGraphicsEffect(shadow)


class GradientContactCard(QFrame):
    """Grote contactkaart met magenta→roze gradient + ronde actieknoppen.

    Toont avatar/initialen, naam, vier actieknoppen en een infoblok.
    De OperatorDashboard koppelt de telefoon/ophang-acties hieraan.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("contact_card")
        self.setMinimumWidth(360)
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 30, 26, 26)
        lay.setSpacing(0)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.avatar = _AvatarBox("VitaCall", "#bf5af2")
        self.avatar.setFixedSize(120, 120)
        lay.addWidget(self.avatar, alignment=Qt.AlignmentFlag.AlignHCenter)

        lay.addSpacing(16)
        self.name_label = QLabel("geen oproep")
        self.name_label.setStyleSheet(
            "color: white; font-size: 30px; font-weight: 800; letter-spacing: -0.6px;"
        )
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self.name_label)

        lay.addSpacing(4)
        self.sub_label = QLabel("wacht op binnenkomende oproep")
        self.sub_label.setStyleSheet(
            "color: rgba(255,255,255,0.82); font-size: 13px; font-weight: 500;"
        )
        self.sub_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self.sub_label)

        lay.addSpacing(18)
        # Vier ronde actieknoppen (message / phone / video / mail).
        row = QHBoxLayout()
        row.setSpacing(16)
        row.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.btn_message = RoundActionButton()
        self.btn_phone = RoundActionButton()
        self.btn_video = RoundActionButton()
        self.btn_mail = RoundActionButton()
        for b in (self.btn_message, self.btn_phone, self.btn_video, self.btn_mail):
            row.addWidget(b)
        lay.addLayout(row)

        lay.addSpacing(22)
        # Glazen info-blok (zoals 'Contact Photo and Poster' / mobile / work).
        self.info = QFrame()
        self.info.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.18); border-radius: 14px; }"
        )
        il = QVBoxLayout(self.info)
        il.setContentsMargins(16, 14, 16, 14)
        il.setSpacing(10)
        self._info_rows: list[tuple[QLabel, QLabel]] = []
        for key, val in (("status", "idle"), ("verbinding", "-"), ("transcript", "-")):
            k = QLabel(key)
            k.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 11px; font-weight: 600;")
            v = QLabel(val)
            v.setStyleSheet("color: white; font-size: 14px; font-weight: 600;")
            il.addWidget(k)
            il.addWidget(v)
            self._info_rows.append((k, v))
        lay.addWidget(self.info)
        lay.addStretch(1)

    def set_contact(self, name: str, sub: str, color: str = "#bf5af2") -> None:
        self.name_label.setText(name)
        self.sub_label.setText(sub)
        self.avatar.initials = _initials(name)
        self.avatar.color = color
        self.avatar.update()

    def set_info(self, status: str, verbinding: str, transcript: str) -> None:
        self._info_rows[0][1].setText(status)
        self._info_rows[1][1].setText(verbinding)
        self._info_rows[2][1].setText(transcript)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 18, 18)
        # Solide accentvulling (geen gradient).
        p.fillPath(path, QColor(PANEL_FILL))
        super().paintEvent(_event)


class StatCard(QFrame):
    """Compacte stat-card met label + waarde (licht thema)."""

    def __init__(self, label: str, value: str, color: str | None = None) -> None:
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(3)
        lbl = QLabel(label.upper())
        lbl.setObjectName("stat_label")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("stat_value")
        if color:
            self.value_label.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: 800;")
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
        p.setBrush(QColor("#e6e6ea"))
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
