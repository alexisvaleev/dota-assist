"""Скриншот игровой области -> draft_screen.png рядом с проектом.

Координаты калибровки отсчитываются от клиентской области окна Dota
(wininfo), поэтому снимок делаем по той же логике, что и watcher.
На Windows берётся окно Dota; иначе — монитор из calibration.json.

Открой экран драфта (лобби/демо пик) и запусти:
  python scripts/screenshot_for_calib.py
"""
import json
import sys
from pathlib import Path

import mss
import mss.tools

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
import wininfo  # noqa: E402


def main():
    with mss.mss() as sct:
        rect = wininfo.dota_client_rect()
        if rect:
            x, y, w, h = rect
            region = {"left": x, "top": y, "width": w, "height": h}
            note = f"окно Dota {w}x{h}"
        else:
            mon_idx = 1
            cal_p = ROOT / "app" / "calibration.json"
            if cal_p.exists():
                mon_idx = int(json.loads(cal_p.read_text(
                    encoding="utf-8")).get("monitor", 1))
            mon = sct.monitors[mon_idx] if mon_idx < len(sct.monitors) \
                else sct.monitors[1]
            region = mon
            note = f"монитор {mon_idx}"
        shot = sct.grab(region)
        out = ROOT / "draft_screen.png"
        mss.tools.to_png(shot.rgb, shot.size, output=str(out))
        print(f"saved {out} ({shot.size.width}x{shot.size.height}, {note})")
        print("Если автокалибровка не сработает — замерь слоты "
              "[x,y,w,h] и впиши в app/calibration.json, "
              f"resolution = [{shot.size.width}, {shot.size.height}]")


if __name__ == "__main__":
    sys.exit(main())
