"""Захват экрана во время драфта: читает слоты портретов и банов.

Исправления v2:
- монитор из calibration.monitor (по умолчанию 1, а не monitors[0] —
  объединённый виртуальный экран съезжал при двух мониторах);
- координаты масштабируются от calibration.resolution к реальному;
- распознаём только героев (иконок ролей в Ranked AP нет);
- передаём confidence (худший score) и margin — для решения «доверять ли»;
- баны читаются из отдельного ряда слотов.
"""
import threading
import time
from typing import Callable

import mss
import numpy as np

from recognizer import Recognizer, load_calibration


def _crop(img: np.ndarray, box):
    x, y, w, h = box
    if w <= 0 or h <= 0:
        return img[0:0, 0:0]
    return img[y:y + h, x:x + w]


class DraftWatcher(threading.Thread):
    def __init__(self, on_change: Callable[[dict], None],
                 interval_ms: int = 500):
        super().__init__(daemon=True, name="draft-watcher")
        self.on_change = on_change
        self.interval = interval_ms / 1000
        self.rec = Recognizer()
        self.cal = load_calibration()
        self.rec.threshold = self.cal.get("match_threshold", 0.82)
        self.min_margin = self.cal.get("min_margin", 0.06)
        self.monitor = int(self.cal.get("monitor", 1))

        self.enabled = False
        self.my_side = "radiant"        # Radiant слева; override из main
        self.state: dict = {}
        self._history: dict[tuple[str, int], list[str | None]] = {}
        self._stop_flag = threading.Event()

    # ---------- helpers ----------

    def _stable(self, key: tuple[str, int], hero: str | None) -> str | None:
        h = self._history.setdefault(key, [])
        h.append(hero)
        del h[:-3]
        votes = [v for v in h if v]
        # герой засчитывается после 2 подряд одинаковых кадров
        if len(votes) >= 2 and votes[-1] == votes[-2]:
            return votes[-1]
        return None

    def set_side(self, team_name: str):
        if team_name in ("radiant", "dire"):
            self.my_side = team_name

    def _scale(self, img_w: int, img_h: int):
        rw, rh = self.cal.get("resolution", [img_w, img_h])
        return img_w / max(rw, 1), img_h / max(rh, 1)

    def _slots(self, group: str, sx: float, sy: float) -> list[list[int]]:
        raw = self.cal.get(group)
        if isinstance(raw, dict):
            raw = raw.get("slots", [])
        out = []
        for x, y, w, h in raw or []:
            out.append([int(x * sx), int(y * sy), int(w * sx), int(h * sy)])
        return out

    def _read_slots(self, img, slots, key_prefix: str):
        """-> (heroes, unknown_idx, min_score)"""
        heroes, unknown, worst = [], [], 1.0
        for i, box in enumerate(slots):
            crop = _crop(img, box)
            if crop.size == 0:
                heroes.append(None)
                continue
            hero, score = self.rec.hero(crop)
            hero = self._stable((key_prefix, i), hero)
            if hero:
                heroes.append(hero)
                worst = min(worst, score)
            elif crop.std() > 8:     # что-то отрисовано, но не узнали
                heroes.append(None)
                unknown.append(i)
            else:
                heroes.append(None)
        return heroes, unknown, worst

    # ---------- main loop ----------

    def _tick(self, sct):
        mons = sct.monitors
        mon = mons[self.monitor] if self.monitor < len(mons) else mons[1]
        img = np.asarray(sct.grab(mon))[:, :, :3]
        sx, sy = self._scale(img.shape[1], img.shape[0])

        radiant_key = "team_right" if self.cal.get("radiant_on_right") \
            else "team_left"
        dire_key = "team_left" if radiant_key == "team_right" else "team_right"
        enemy_key = radiant_key if self.my_side == "dire" else dire_key
        ally_key = dire_key if self.my_side == "dire" else radiant_key

        e, e_unk, e_score = self._read_slots(
            img, self._slots(enemy_key, sx, sy), "e")
        a, a_unk, a_score = self._read_slots(
            img, self._slots(ally_key, sx, sy), "a")
        bans, _, _ = self._read_slots(
            img, self._slots("bans", sx, sy), "b")

        new = {
            "enemy_picks": [h for h in e if h],
            "ally_picks": [h for h in a if h],
            "bans": [b for b in bans if b],
            "unknown_slots": len(e_unk),
            "confidence": round(min(e_score, a_score), 3),
        }
        if new != self.state:
            self.state = new
            self.on_change(new)

    def run(self):
        with mss.mss() as sct:
            while not self._stop_flag.is_set():
                if self.enabled:
                    try:
                        self._tick(sct)
                    except Exception as e:
                        print(f"[draft_watcher] {e}")
                time.sleep(self.interval)

    def stop(self):
        self._stop_flag.set()
