"""Авто-калибровка слотов драфта по скриншоту.

Идея: слоты пиков — прямоугольные карточки по левому/правому краю,
баны — ряд мелких квадратов сверху. Находим прямоугольные контуры,
кластеризуем по колонке и отсеиваем сетку героев (она в центре).
Получившиеся слоты прогоняем через Recognizer для оценки качества.

Ничего не трогаем, если уверенности мало — вернём None и останется
ручная калибровка.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from paths import user_dir


def _squares(img: np.ndarray) -> list[list[int]]:
    """Кандидаты-«плитки»: прямоугольные контуры в разумном размере."""
    h, w = img.shape[:2]
    lo, hi = int(min(h, w) * 0.035), int(min(h, w) * 0.16)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 160)
    edges = cv2.dilate(edges, np.ones((2, 2), np.uint8))
    cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cnts:
        x, y, cw, ch = cv2.boundingRect(c)
        if not (lo <= cw <= hi and lo <= ch <= hi):
            continue
        if not (0.8 <= cw / ch <= 1.25):
            continue
        out.append([x, y, cw, ch])
    return out


def _column_cluster(cands, side: str, W: int) -> list[list[int]]:
    """Одна колонка из 5 слотов: близкий x, равномерный шаг по y."""
    cx = lambda r: r[0] + r[2] // 2  # noqa: E731
    if side == "left":
        edge = [r for r in cands if cx(r) < W * 0.22]
    else:
        edge = [r for r in cands if cx(r) > W * 0.78]
    if not edge:
        return []
    edge.sort(key=lambda r: r[0])
    # самая густая колонка по x
    best = []
    for r in edge:
        col = [q for q in edge if abs((q[0] + q[2] / 2)
                                      - (r[0] + r[2] / 2)) < r[2] * 0.5]
        if len(col) > len(best):
            best = col
    if len(best) < 3:
        return []
    best.sort(key=lambda r: r[1])
    # убираем дубли-вложенности: оставляем ближайший по размеру к медиане
    med = sorted(r[2] for r in best)[len(best) // 2]
    best = [r for r in best if abs(r[2] - med) <= med * 0.35]
    return best[:5]


def _ban_row(cands, W: int, H: int) -> list[list[int]]:
    """Баны — мелкие квадраты рядом в верхней полосе."""
    top = [r for r in cands if r[1] < H * 0.16
           and W * 0.15 < r[0] < W * 0.85]
    top.sort(key=lambda r: r[0])
    # ряд: одинаковая высота и перекрытие по y
    if len(top) < 4:
        return []
    med_y = np.median([r[1] for r in top])
    row = [r for r in top if abs(r[1] - med_y) < r[3] * 0.6]
    return row[:14]


def auto_calibrate(img: np.ndarray, monitor: int = 1) -> dict | None:
    """-> calibration dict | None, если уверенности мало."""
    H, W = img.shape[:2]
    cands = _squares(img)
    left = _column_cluster(cands, "left", W)
    right = _column_cluster(cands, "right", W)
    if len(left) < 3 or len(right) < 3:
        return None
    # до 5 ровных слотов
    def pad5(col):
        return (col + [[0, 0, 0, 0]] * 5)[:5]
    cal = {
        "resolution": [W, H],
        "monitor": monitor,
        "radiant_on_right": False,
        "match_threshold": 0.82,
        "min_margin": 0.06,
        "auto": True,
        "team_left": {"slots": pad5(left)},
        "team_right": {"slots": pad5(right)},
        "bans": _ban_row(cands, W, H),
    }
    return cal


def quality(rec, img: np.ndarray, cal: dict) -> tuple[int, int]:
    """Сколько слотов распозналось уверенно (score >= threshold)."""
    ok = total = 0
    for side in ("team_left", "team_right", "bans"):
        slots = cal[side]["slots"] if isinstance(cal.get(side), dict) \
            else cal.get(side, [])
        for x, y, w, h in slots:
            if w <= 0:
                continue
            total += 1
            name, score, _ = rec.hero_top2(img[y:y + h, x:x + w])
            if name:
                ok += 1
    return ok, total


def save_calibration(cal: dict) -> Path:
    """Кладётся в user_dir — поверх bundled/external (см. paths.layered)."""
    p = user_dir() / "app" / "calibration.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    cal["_comment"] = ("Авто-калибровка. Перезапишет bundled; правь вручную "
                       "при сбоях.")
    p.write_text(json.dumps(cal, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    return p
