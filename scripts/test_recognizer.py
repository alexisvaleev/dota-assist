"""Офлайн-проверка распознавания: прогоняет recognizer по сохранённому
скриншоту драфта и печатает, что совпало в каждом слоте, со score.

  python scripts/test_recognizer.py [draft_screen.png] [-v]

Сначала калибровка app/calibration.json (scripts/screenshot_for_calib.py).
Критерий go/no-go из docs/findings.md: победитель ≥0.9, второй ≤0.75.
"""
import argparse
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from recognizer import Recognizer, load_calibration  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image", nargs="?", default=str(ROOT / "draft_screen.png"))
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    img = cv2.imread(args.image)
    if img is None:
        sys.exit(f"не найден скриншот: {args.image}")

    rec = Recognizer()
    cal = load_calibration()
    rec.threshold = cal.get("match_threshold", 0.82)
    if not rec.hero_templates:
        sys.exit("data/icons пуст — сначала python scripts/extract_icons.py")

    rw, rh = cal.get("resolution", list(img.shape[:2][::-1]))
    sx, sy = img.shape[1] / rw, img.shape[0] / rh
    print(f"шаблонов: {sum(len(v) for v in rec.hero_templates.values())} "
          f"героев: {len(rec.hero_templates)}  scale={sx:.2f}x{sy:.2f}\n")

    good = total = 0
    for side in ("team_left", "team_right", "bans"):
        slots = cal.get(side)
        if isinstance(slots, dict):
            slots = slots.get("slots", [])
        print(f"== {side} ==")
        for i, (x, y, w, h) in enumerate(slots):
            if not w:
                continue
            total += 1
            crop = img[int(y * sy):int((y + h) * sy),
                       int(x * sx):int((x + w) * sx)]
            name, score, margin = rec.hero_top2(crop)
            if name:
                good += 1
            print(f"  слот {i}: {name or '?'}  score={score:.3f} "
                  f"margin={margin:.3f}")
        print()
    print(f"распознано {good}/{total}; критерий: score≥{rec.threshold}, "
          f"margin≥{cal.get('min_margin', 0.06)}")


if __name__ == "__main__":
    main()
