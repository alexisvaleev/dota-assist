"""Безрамочный полупрозрачный оверлей поверх Dota.

По умолчанию — click-through (клики уходят в игру). Ctrl+Shift+D
переключает в интерактивный режим: кнопки стороны и позиции 1-5,
перетаскивание окна.
"""
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QButtonGroup,
)

from paths import layered_dir


def icons_dir() -> Path:
    """Лениво: иконки могут докачаться bootstrap'ом уже после старта."""
    return layered_dir("data/icons")

POSITIONS = ["1", "2", "3", "4", "5"]


class Bus(QObject):
    draft_update = pyqtSignal(dict)
    items_update = pyqtSignal(dict)
    status = pyqtSignal(str)
    side_changed = pyqtSignal(str)       # "radiant" | "dire"
    pos_changed = pyqtSignal(str)        # "1".."5" | "" (авто)
    side_detected = pyqtSignal(str)
    toggle_interactive = pyqtSignal()
    calibrate = pyqtSignal()             # принудительная авто-калибровка
    update_found = pyqtSignal(dict)      # {"tag", "url", ...}
    update_requested = pyqtSignal()      # пользователь согласился обновиться
    quit_app = pyqtSignal()              # обновление готово -> выход+подмена
    draft_raw = pyqtSignal(dict)         # снимок драфта из watcher-потока
    gsi_raw = pyqtSignal(object)         # GSI-состояние из Flask-потока


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
                         o.get("width", 340), 10)

        self.bus = Bus()

        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(8, 8, 8, 8)
        self.setStyleSheet(
            "background: rgba(10,10,15,200); color:#eee;"
            "border:1px solid #333; border-radius:8px;"
            "QLabel{font: 12px 'Segoe UI';}"
            "QPushButton{font:11px 'Segoe UI'; padding:2px 8px;"
            " background:#223; border:1px solid #445; border-radius:4px;}"
            "QPushButton:checked{background:#2e8b57; color:#fff;"
            " border:1px solid #8fd; font-weight:bold;}")

        self.title = QLabel("Dota Assist")
        self.title.setStyleSheet("font-weight:bold; color:#8cf;")
        self.lay.addWidget(self.title)

        self.status_lab = QLabel("")
        self.status_lab.setStyleSheet("color:#777; font-size:10px;")
        self.lay.addWidget(self.status_lab)

        # --- панель управления (только в интерактивном режиме) ---
        self.ctrl = QWidget()
        cl = QHBoxLayout(self.ctrl)
        cl.setContentsMargins(0, 0, 0, 0)

        self.side_btn = QPushButton("Radiant")
        self.side_btn.setCheckable(True)
        self.side_btn.setMinimumWidth(74)
        self.side_btn.toggled.connect(self._side_toggled)
        cl.addWidget(self.side_btn)

        self.update_btn = QPushButton()
        self.update_btn.hide()
        self.update_btn.clicked.connect(self.bus.update_requested)
        cl.addWidget(self.update_btn)

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

        self.calib_btn = QPushButton("Калиб.")
        self.calib_btn.setToolTip("Авто-детект слотов драфта на экране")
        self.calib_btn.clicked.connect(lambda: self.bus.calibrate.emit())
        cl.addWidget(self.calib_btn)
        cl.addStretch(1)
        self.ctrl.hide()
        self.lay.addWidget(self.ctrl)
        # ---------------------------------------------------------

        self.body = QVBoxLayout()
        self.lay.addLayout(self.body)

        self.bus.draft_update.connect(self.show_draft)
        self.bus.items_update.connect(self.show_items)
        self.bus.status.connect(self.status_lab.setText)
        self.bus.side_detected.connect(self.set_side_display)
        self.bus.toggle_interactive.connect(
            lambda: self.set_interactive(not self.interactive))
        self.bus.update_found.connect(self._update_found)

    # ---------- режимы ----------

    def set_interactive(self, on: bool):
        self.interactive = on
        self.ctrl.setVisible(on)
        flags = self._flags
        if not on:
            flags |= Qt.WindowType.WindowTransparentForInput
        self.setWindowFlags(flags)
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
            self.bus.pos_changed.emit(pos)
        elif not any(b.isChecked() for b in self.pos_btns.values()):
            self.bus.pos_changed.emit("")     # сняли выбор — авто

    def _update_found(self, info: dict):
        tag = info.get("tag", "")
        self.update_btn.setText(f"⟳ {tag}")
        self.update_btn.setToolTip("Скачать и установить обновление")
        self.update_btn.show()
        self.status_lab.setText(f"доступно обновление {tag}")
        self.adjustSize()

    def set_side_display(self, side: str):
        self.side_btn.blockSignals(True)
        self.side_btn.setChecked(side == "dire")
        self.side_btn.setText("Dire" if side == "dire" else "Radiant")
        self.side_btn.blockSignals(False)

    # ---------- drag ----------

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

    # ---------- контент ----------

    def _clear(self, lay: QVBoxLayout | None = None):
        # takeAt на вложенном QHBoxLayout отдаёт layout, а не widget —
        # без рекурсии его виджеты остаются детьми окна и наползают
        # на следующий show_draft.
        lay = lay or self.body
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                self._clear(it.layout())

    def _icon_label(self, hero_dir: str, size: int = 48) -> QLabel:
        lab = QLabel()
        d = icons_dir() / hero_dir
        png = next(d.glob("*.png"), None) if d.exists() else None
        if png:
            pm = QPixmap(str(png)).scaled(
                size, size, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            lab.setPixmap(pm)
        else:
            lab.setText(hero_dir[:3])
        return lab

    def show_draft(self, d: dict):
        self._clear()
        phase = d.get("phase", "Драфт")
        conf = d.get("confidence", 1.0)
        self.title.setText(f"Драфт — {phase}")

        if d.get("calib"):
            c = QLabel(d["calib"])
            c.setStyleSheet("color:#7ad; font-size:10px;")
            self.body.addWidget(c)

        if not d.get("reliable", True):
            warn = QLabel(
                f"⚠ распознавание неточное "
                f"(conf {conf:.2f}, нераспозн. слотов "
                f"{d.get('unknown_slots', 0)}) — рекомендации примерные")
            warn.setStyleSheet("color:#e80; font-size:10px;")
            warn.setWordWrap(True)
            self.body.addWidget(warn)

        for w_text in d.get("warnings") or []:
            w = QLabel(f"⚠ {w_text}")
            w.setStyleSheet("color:#e80; font-size:10px;")
            self.body.addWidget(w)

        row = QHBoxLayout()
        row.addWidget(QLabel("Враги:"))
        for name in d.get("enemy_picks", []):
            row.addWidget(self._icon_label(name, 36))
        for _ in range(d.get("unknown_slots", 0)):
            row.addWidget(QLabel("[?]"))
        row.addStretch(1)
        self.body.addLayout(row)

        bans = d.get("bans", [])
        if bans:
            row = QHBoxLayout()
            row.addWidget(QLabel("Баны:"))
            for name in bans[:12]:
                ic = self._icon_label(name, 24)
                ic.setStyleSheet("opacity:0.5;")
                row.addWidget(ic)
            row.addStretch(1)
            self.body.addLayout(row)

        self.body.addWidget(QLabel("Топ пики:"))
        for icon_name, disp, score, why in d.get("top", []):
            h = QHBoxLayout()
            h.addWidget(self._icon_label(icon_name, 40))
            v = QLabel(f"{disp}  <b>{score:+.1f}</b>")
            v.setToolTip("Сумма слагаемых относительно нейтрали: "
                         "мета(винрейт−50) + контрпик + синергия "
                         "+ твой пул + состав")
            w = QLabel(f"<i>{why}</i>")
            w.setStyleSheet("color:#9a9; font-size:10px;")
            col = QVBoxLayout()
            col.addWidget(v)
            col.addWidget(w)
            h.addLayout(col)
            h.addStretch(1)
            self.body.addLayout(h)
        self.adjustSize()

    def show_items(self, d: dict):
        self._clear()
        self.title.setText(f"Сборка — {d.get('hero', '')}")
        for it in d.get("items", []):
            if isinstance(it, dict):
                name = it["item"]
                mark = "" if it.get("affordable", True) \
                    else f"  (нужно ещё {it.get('need_gold', 0)}g)"
                self.body.addWidget(
                    QLabel(f"• {name} — {it.get('reason', '')}{mark}"))
            else:
                self.body.addWidget(QLabel("• " + str(it)))
        self.adjustSize()


def run_overlay(cfg: dict) -> tuple[QApplication, Overlay]:
    app = QApplication.instance() or QApplication(sys.argv)
    w = Overlay(cfg)
    w.show()
    return app, w
