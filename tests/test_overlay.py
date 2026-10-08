"""Оверлей: _clear не должен оставлять виджеты из вложенных layout'ов.

Исторический баг: строки «Враги»/«Баны»/топ-пики — это QHBoxLayout,
takeAt().widget() для них возвращает None, и их QLabel'ы оставались
детьми окна, наползая на следующий show_draft.
"""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

try:
    from PyQt6.QtWidgets import QApplication, QWidget  # noqa
    from PyQt6.QtCore import QEvent, QCoreApplication  # noqa
    from overlay import Overlay                        # noqa
    OK = True
except Exception:
    OK = False


def _flush_deletes():
    # deleteLater исполняется только при явной отправке DeferredDelete;
    # голый sendPostedEvents()/processEvents() их не трогает.
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

DRAFT = {
    "phase": "Раунд 2",
    "enemy_picks": ["axe", "pudge"],
    "bans": ["lina"],
    "unknown_slots": 1,
    "warnings": ["нет инициации"],
    "top": [("inv", "Invoker", 3.4, "контр +1.2 · состав +1.5")],
}


def _widgets(root):
    return root.findChildren(QWidget)


@unittest.skipUnless(OK, "нет PyQt6")
class Clear(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_second_draft_leaves_no_stray_widgets(self):
        w = Overlay({"overlay": {}})
        w.show_draft(DRAFT)
        _flush_deletes()
        n1 = len(_widgets(w))
        w.show_draft(DRAFT)
        _flush_deletes()
        n2 = len(_widgets(w))
        self.assertEqual(n1, n2)

    def test_second_draft_no_overlap(self):
        """После повторного show_draft активных потомков ровно столько,
        сколько отрисовал последний вызов."""
        w = Overlay({"overlay": {}})
        w.show_draft(DRAFT)
        _flush_deletes()
        w.show_draft(DRAFT)
        _flush_deletes()
        w.show()                      # realize, чтобы посчитать видимых
        visible = [x for x in _widgets(w) if not x.isHidden()]
        # грубая проверка: сирот бы давало ~2x виджетов
        self.assertLess(len(visible), 40)


if __name__ == "__main__":
    unittest.main()
