"""Grab the screen and save draft_screen.png next to the project —
use it in Paint/GIMP to measure slot rectangles for calibration.json.

Run this while the draft screen is open (e.g. in a lobby/demo pick).
  python scripts/screenshot_for_calib.py
"""
import sys
from pathlib import Path

import mss
import mss.tools

ROOT = Path(__file__).resolve().parent.parent


def main():
    with mss.mss() as sct:
        mon = sct.monitors[0]
        shot = sct.grab(mon)
        out = ROOT / "draft_screen.png"
        mss.tools.to_png(shot.rgb, shot.size, output=str(out))
        print(f"saved {out} ({shot.size.width}x{shot.size.height})")
        print("Замерь слоты: [x, y, w, h] портрета и иконки роли для "
              "каждого из 5 слотов каждой команды → app/calibration.json")


if __name__ == "__main__":
    sys.exit(main())
