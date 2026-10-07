"""Скриншот монитора с игрой -> draft_screen.png рядом с проектом.

Открой экран драфта (лобби/демо пик) и запусти:
  python scripts/screenshot_for_calib.py

Монитор берётся из app/calibration.json -> "monitor" (mss: 1 = первый).
Замерь в Paint/GIMP прямоугольники слотов [x,y,w,h] и впиши в
calibration.json: team_left, team_right (по 5), bans.
"""
import json
import sys
from pathlib import Path

import mss
import mss.tools

ROOT = Path(__file__).resolve().parent.parent


def main():
    cal_p = ROOT / "app" / "calibration.json"
    mon_idx = 1
    if cal_p.exists():
        mon_idx = int(json.loads(cal_p.read_text(
            encoding="utf-8")).get("monitor", 1))
    with mss.mss() as sct:
        mon = sct.monitors[mon_idx] if mon_idx < len(sct.monitors) \
            else sct.monitors[1]
        shot = sct.grab(mon)
        out = ROOT / "draft_screen.png"
        mss.tools.to_png(shot.rgb, shot.size, output=str(out))
        print(f"saved {out} ({shot.size.width}x{shot.size.height}, "
              f"monitor {mon_idx})")
        print("Впиши координаты слотов в app/calibration.json и задай "
              "\"resolution\": [%d, %d]" % (shot.size.width,
                                            shot.size.height))


if __name__ == "__main__":
    sys.exit(main())
