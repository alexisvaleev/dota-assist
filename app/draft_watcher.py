"""Захват экрана во время драфта: слоты портретов и банов.

v3:
- область захвата = клиентская область окна Dota (wininfo), не весь монитор;
  координаты калибровки — в пикселях этой области, resolution = её размер;
- если слоты не откалиброваны (нули), авто-детект по контурам каждые ~2 с;
- уверенность и «нераспознанные слоты» пробрасываются в оверлей.
"""
import threading
import time
from typing import Callable

import mss
import numpy as np

from recognizer import Recognizer, load_calibration
import wininfo
import autocalib


def _crop(img: np.ndarray, box):
    x, y, w, h = box
    if w <= 0 or h <= 0:
        return img[0:0, 0:0]
    return img[y:y + h, x:x + w]


def _empty_slots(cal: dict) -> bool:
    slots = (cal.get("team_left") or {}).get("slots") or []
    return not any(s[2] > 0 for s in slots)


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

        # без GSI CV — единственный источник драфта: стартуем включённым;
        # on_gsi выключает на состояниях, где драфта заведомо нет
        self.enabled = True
        self.my_side = "radiant"        # Radiant слева; override из main
        self.state: dict = {}
        self._history: dict[tuple[str, int], list[str | None]] = {}
        self._stop_flag = threading.Event()
        self._calib_next = 0.0          # когда пробовать автокалибровку
        self.calib_status = ""          # текст для оверлея
        self.force_calib = False        # ручной триггер из оверлея

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

    def reset(self):
        """Между играми: забыть голоса стабилизации и прошлый снимок,
        иначе первый кадр нового драфта сравнивается со старым."""
        self._history.clear()
        self.state = {}

    def _grab(self, sct) -> np.ndarray:
        """Кадр игровой области: окно Dota, либо монитор из калибровки."""
        rect = wininfo.dota_client_rect()
        if rect:
            x, y, w, h = rect
            shot = sct.grab({"left": x, "top": y, "width": w,
                             "height": h})
        else:
            mons = sct.monitors
            mon = mons[self.monitor] if self.monitor < len(mons) \
                else mons[1]
            shot = sct.grab(mon)
        return np.asarray(shot)[:, :, :3]

    def _scale(self, img_w: int, img_h: int):
        rw, rh = self.cal.get("resolution", [img_w, img_h])
        return img_w / max(rw, 1), img_h / max(rh, 1)

    def _slots(self, group: str, sx: float, sy: float) -> list[list[int]]:
        raw = self.cal.get(group)
        if isinstance(raw, dict):
            raw = raw.get("slots", [])
        return [[int(x * sx), int(y * sy), int(w * sx), int(h * sy)]
                for x, y, w, h in (raw or [])]

    def _read_slots(self, img, slots, key_prefix: str):
        """-> (heroes, unknown_idx, worst_score | None).

        Герой принимается, только если score >= threshold (проверяет
        hero_top2) И margin >= self.min_margin. Высокий score при
        малом margin — два похожих кандидата (варианты аркан): лучшему
        не доверяем, слот считается нераспознанным.
        """
        heroes, unknown = [], []
        worst: float | None = None      # min score по распознанным
        for i, box in enumerate(slots):
            crop = _crop(img, box)
            if crop.size == 0:
                heroes.append(None)
                continue
            name, score, margin = self.rec.hero_top2(crop)
            if name is not None and margin < self.min_margin:
                name = None             # score ок, но второй кандидат рядом
            hero = self._stable((key_prefix, i), name)
            if hero:
                heroes.append(hero)
                worst = score if worst is None else min(worst, score)
            elif crop.std() > 8:
                heroes.append(None)
                unknown.append(i)
            else:
                heroes.append(None)
        return heroes, unknown, worst

    # ---------- автокалибровка ----------

    def _maybe_autocalib(self, img: np.ndarray):
        if not (_empty_slots(self.cal) or self.force_calib):
            return
        if time.time() < self._calib_next:
            return
        self._calib_next = time.time() + 2.0
        self.force_calib = False
        cal = autocalib.auto_calibrate(img, monitor=self.monitor)
        if not cal:
            self.calib_status = "автокалибровка: слоты не найдены"
            return
        ok, total = autocalib.quality(self.rec, img, cal)
        if total and ok < 2:
            self.calib_status = (f"автокалибровка: {ok}/{total} "
                                 "— слоты не похожи на пики")
            return
        p = autocalib.save_calibration(cal)
        self.cal = cal
        self.calib_status = f"автокалибровка ok ({ok}/{total}) -> {p.name}"

    # ---------- main loop ----------

    def _tick(self, sct):
        img = self._grab(sct)
        if _empty_slots(self.cal) or self.force_calib:
            self._maybe_autocalib(img)
            if _empty_slots(self.cal):
                return
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

        # Честная confidence: min score по распознанным слотам, уменьшенный
        # пропорционально доле «занятых, но не распознанных» слотов.
        # Ничего не распознано -> 0.0 (а не 1.0, как при старте с 1.0).
        recognized = sum(1 for h in e + a if h)
        occupied = recognized + len(e_unk) + len(a_unk)
        scores = [s for s in (e_score, a_score) if s is not None]
        conf = min(scores) if scores else 0.0
        if occupied:
            conf *= recognized / occupied

        new = {
            "enemy_picks": [h for h in e if h],
            "ally_picks": [h for h in a if h],
            "bans": [b for b in bans if b],
            "unknown_slots": len(e_unk) + len(a_unk),
            "confidence": round(conf, 3),
            "calib": self.calib_status,
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
