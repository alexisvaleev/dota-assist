"""OpenCV template matching: crop слота -> герой + уверенность.

Шаблоны: <user_dir>/data/icons/<hero_short_name>/*.png (все варианты
аркан/персон из VPK). Resize шаблона под слот делается один раз и
кэшируется — без этого 300+ ресайзов на слот каждые 500 мс.

Ролей на экране Ranked AP нет — распознаём только героев и баны.
"""
import json
from pathlib import Path

import cv2
import numpy as np

from paths import layered_dir, layered_file


def icon_dirs() -> list[Path]:
    """Лениво: иконки могут докачаться bootstrap'ом уже после импорта
    модуля — резолвим слои при каждой загрузке шаблонов."""
    # иконки в appdata (fetch_icons/extract_icons кладут туда) либо
    # рядом с репо/exe
    return [layered_dir("data/icons")]


class Recognizer:
    def __init__(self):
        self.threshold = 0.82
        self.hero_templates: dict[str, list[np.ndarray]] = {}
        self._scaled: dict[tuple[int, int, int], np.ndarray] = {}
        self._load()

    def reload(self):
        """Перечитать шаблоны с диска — после того как bootstrap докачал
        иконки. Кадр за кадром шаблоны с диска не читаются: только явным
        вызовом reload()."""
        self.hero_templates.clear()
        self._scaled.clear()          # ключи — id() старых шаблонов
        self._load()

    def _load(self):
        for icons in icon_dirs():
            if not icons.exists():
                continue
            for hero_dir in icons.iterdir():
                if not hero_dir.is_dir():
                    continue
                tpls = []
                for f in hero_dir.glob("*.png"):
                    img = cv2.imread(str(f))
                    if img is not None:
                        tpls.append(img)
                if tpls:
                    self.hero_templates.setdefault(hero_dir.name,
                                                   []).extend(tpls)
            if self.hero_templates:
                break          # не смешиваем слои: appdata > repo

    def _scaled_tpl(self, tpl: np.ndarray, w: int, h: int) -> np.ndarray:
        key = (id(tpl), w, h)
        s = self._scaled.get(key)
        if s is None:
            s = cv2.resize(tpl, (w, h))
            if len(self._scaled) > 4000:      # страховка от роста памяти
                self._scaled.clear()
            self._scaled[key] = s
        return s

    def hero(self, crop: np.ndarray) -> tuple[str | None, float]:
        """(short_name | None, best_score). None = слот не распознан."""
        name, score, _margin = self.hero_top2(crop)
        return name, score

    def hero_top2(self, crop: np.ndarray) -> tuple[str | None, float, float]:
        """(name, best, margin = best - second).
        margin — запас уверенности: если второй кандидат рядом, распознаванию
        доверять нельзя даже при высоком best."""
        if crop.size == 0:
            return None, 0.0, 0.0
        h, w = crop.shape[:2]
        best1, best2, name = 0.0, 0.0, None
        for hn, tpls in self.hero_templates.items():
            for tpl in tpls:
                t = self._scaled_tpl(tpl, w, h)
                s = float(cv2.matchTemplate(crop, t, cv2.TM_CCOEFF_NORMED)[0][0])
                if s > best1:
                    best1, best2, name = s, best1, hn
                elif s > best2:
                    best2 = s
        if best1 >= self.threshold:
            return name, best1, best1 - best2
        return None, best1, best1 - best2


def load_calibration() -> dict:
    p = layered_file("app/calibration.json")
    return json.loads(p.read_text(encoding="utf-8"))
