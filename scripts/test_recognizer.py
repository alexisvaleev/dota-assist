"""Offline accuracy test: run the recognizer over a saved draft screenshot
and print what each slot matched, with scores.

  python scripts/test_recognizer.py [draft_screen.png] [--verbose]

Calibrate app/calibration.json first, and capture the screenshot via
scripts/screenshot_for_calib.py while a draft screen is open.
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

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

    print(f"шаблонов: {sum(len(v) for v in rec.hero_templates.values())} "
          f"героев: {len(rec.hero_templates)}\n")

    for side in ("team_left", "team_right"):
        print(f"== {side} ==")
        for i, slot in enumerate(cal[side]["slots"]):
            x, y, w, h = slot["portrait"]
            if w == 0:
                print(f"  слот {i}: не откалиброван")
                continue
            crop = img[y:y + h, x:x + w]
            name, score = rec.hero(crop)
            mark = name or "?"
            print(f"  слот {i}: {mark}  (score {score:.3f})")

            if args.verbose:
                # top-5 candidates across all templates for this crop
                cand = []
                for hn, tpls in rec.hero_templates.items():
                    s = max(rec._match(crop, t) for _, t in tpls)
                    cand.append((s, hn))
                cand.sort(reverse=True)
                for s, hn in cand[:5]:
                    print(f"      {s:.3f}  {hn}")

            rc = slot["role"]
            x, y, w, h = rc
            if w and rec.role_templates:
                r = rec.role(img[y:y + h, x:x + w])
                print(f"          роль: {r or '?'}")
        print()


if __name__ == "__main__":
    main()
