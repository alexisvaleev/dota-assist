"""Frameless, translucent, always-on-top overlay window.

Default mode is click-through (clicks pass to the game). A global hotkey
toggles interactive mode, which reveals the control bar:
  - side button      (Radiant <-> Dire manual override)
  - position buttons (1..5 manual role override)
"""
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QButtonGroup,
)

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "data" / "icons"

POSITIONS = ["1", "2", "3", "4", "5"]
POS_TO_ROLE = {
    "1": "carry", "2": "mid", "3": "offlane",
    "4": "soft_support", "5": "hard_support",
}


class Bus(QObject):
    draft_update = pyqtSignal(dict)      # {enemy_picks, top3:[(name,score,why)]}
    items_update = pyqtSignal(dict)      # {hero, items, enemies}
    status = pyqtSignal(str)
    side_changed = pyqtSignal(str)       # "radiant" | "dire"
    role_changed = pyqtSignal(str)       # role name or "" (auto)
    side_detected = pyqtSignal(str)      # external auto-detect -> UI only
    toggle_interactive = pyqtSignal()    # global hotkey lands here


class Overlay(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        o = cfg.get("overlay", {})
        self.interactive = False
        self._drag_pos = None

        self._flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool)
        self.setWindowFlags(self._flags
                            | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(o.get("opacity", 0.85))
        self.setGeometry(o.get("x", 20), o.get("y", 200),
                         o.get("width", 320), 10)

        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(8, 8, 8, 8)
        self.setStyleSheet(
            "background: rgba(10,10,15,200); color:#eee;"
            "border:1px solid #333; border-radius:8px;"
            "QLabel{font: 12px 'Segoe UI';}"
            "QPushButton{font:11px 'Segoe UI'; padding:2px 8px;"
            " background:#223; border:1px solid #445; border-radius:4px;}"
            "QPushButton:checked{background:#3a6; color:#fff;}")

        self.title = QLabel("Dota Assist")
        self.title.setStyleSheet("font-weight:bold; color:#8cf;")
        self.lay.addWidget(self.title)

        self.status_lab = QLabel("")
        self.status_lab.setStyleSheet("color:#777; font-size:10px;")
        self.lay.addWidget(self.status_lab)

        # --- control bar (visible only in interactive mode) ---
        self.ctrl = QWidget()
        cl = QHBoxLayout(self.ctrl)
        cl.setContentsMargins(0, 0, 0, 0)

        self.side_btn = QPushButton("Radiant")
        self.side_btn.setCheckable(True)
        self.side_btn.toggled.connect(self._side_toggled)
        cl.addWidget(self.side_btn)

        cl.addWidget(QLabel("Поз:"))
        self.pos_group = QButtonGroup(self)
        self.pos_group.setExclusive(False)
        self.pos_btns = {}
        for p in POSITIONS:
            b = QPushButton(p)
            b.setCheckable(True)
            b.setFixedWidth(26)
            b.toggled.connect(lambda on, p=p: self._pos_toggled(p, on))
            self.pos_group.addButton(b)
            self.pos_btns[p] = b
            cl.addWidget(b)
        cl.addStretch(1)
        self.ctrl.hide()
        self.lay.addWidget(self.ctrl)
        # ----------------------------------------------------

        self.body = QVBoxLayout()
        self.lay.addLayout(self.body)

        self.bus = Bus()
        self.bus.draft_update.connect(self.show_draft)
        self.bus.items_update.connect(self.show_items)
        self.bus.status.connect(self.status_lab.setText)
        self.bus.side_detected.connect(self.set_side_display)
        self.bus.toggle_interactive.connect(
            lambda: self.set_interactive(not self.interactive))

    # ---------- modes ----------

    def set_interactive(self, on: bool):
        self.interactive = on
        self.ctrl.setVisible(on)
        flags = self._flags
        if not on:
            flags |= Qt.WindowType.WindowTransparentForInput
        self.setWindowFlags(flags)   # resets window => needs show()
        self.show()

    def _side_toggled(self, checked: bool):
        side = "dire" if checked else "radiant"
        self.side_btn.setText("Dire" if checked else "Radiant")
        self.bus.side_changed.emit(side)

    def _pos_toggled(self, pos: str, on: bool):
        if on:
            for p, b in self.pos_btns.items():
                if p != pos:
                    b.setChecked(False)
            self.bus.role_changed.emit(POS_TO_ROLE[pos])
        elif not any(b.isChecked() for b in self.pos_btns.values()):
            self.bus.role_changed.emit("")  # back to auto-detect

    def set_side_display(self, side: str):
        """Reflect externally-detected side without re-emitting."""
        self.side_btn.blockSignals(True)
        self.side_btn.setChecked(side == "dire")
        self.side_btn.setText("Dire" if side == "dire" else "Radiant")
        self.side_btn.blockSignals(False)

    # ---------- drag (interactive mode only) ----------

    def mousePressEvent(self, e):
        if self.interactive:
            self._drag_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if self.interactive and self._drag_pos:
            self.move(self.pos() + e.globalPosition().toPoint()
                      - self._drag_pos)
            self._drag_pos = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

    # ---------- content ----------

    def _clear(self):
        while self.body.count():
            w = self.body.takeAt(0).widget()
            if w:
                w.deleteLater()

    def _icon_label(self, hero_dir: str, size: int = 48) -> QLabel:
        lab = QLabel()
        d = ICONS / hero_dir
        png = next(d.glob("*.png"), None) if d.exists() else None
        if png:
            pm = QPixmap(str(png)).scaled(
                size, size, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            lab.setPixmap(pm)
        else:
            lab.setText("?")
        return lab

    def show_draft(self, d: dict):
        self._clear()
        self.title.setText("Драфт")

        row = QHBoxLayout()
        row.addWidget(QLabel("Враги:"))
        for name in d.get("enemy_picks", []):
            row.addWidget(self._icon_label(name, 36))
        for _ in d.get("unknown_slots", []):
            row.addWidget(QLabel("[?]"))
        row.addStretch(1)
        self.body.addLayout(row)

        self.body.addWidget(QLabel("Топ пики:"))
        for icon_name, disp, score, why in d.get("top3", []):
            h = QHBoxLayout()
            h.addWidget(self._icon_label(icon_name, 40))
            v = QLabel(f"{disp}  <b>{score:.1f}</b>  <i>{why}</i>")
            h.addWidget(v)
            h.addStretch(1)
            self.body.addLayout(h)
        self.adjustSize()

    def show_items(self, d: dict):
        self._clear()
        self.title.setText(f"Сборка — {d.get('hero', '')}")
        for it in d.get("items", []):
            self.body.addWidget(QLabel("• " + it))
        self.adjustSize()


def run_overlay(cfg: dict) -> tuple[QApplication, Overlay]:
    app = QApplication.instance() or QApplication(sys.argv)
    w = Overlay(cfg)
    w.show()
    return app, w
