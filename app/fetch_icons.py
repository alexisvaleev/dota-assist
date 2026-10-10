"""Качает базовые иконки героев со Steam CDN в <user_dir>/data/icons/<hero>/.

Никаких внешних тулов — работает из коробки. CDN даёт по одной дефолтной
иконке на героя; арканы/персоны можно добить позже через
scripts/extract_icons.py (VPK, варианты лягут в те же папки).

  python scripts/fetch_icons_cdn.py
"""
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from paths import user_dir, layered_dir  # noqa: E402

CDN = "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes"


def main():
    icons = user_dir() / "data" / "icons"
    heroes = {}
    for d in (user_dir() / "data", layered_dir("data")):
        p = d / "heroes.json"
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
            heroes = raw.get("data", raw)
            break
    if not heroes:
        sys.exit("heroes.json не найден — сначала scripts/fetch_data.py")

    ok = skip = fail = 0
    total = len(heroes)
    with httpx.Client(timeout=30, follow_redirects=True) as c:
        for i, (hid, h) in enumerate(heroes.items()):
            print(f"  icons {i + 1}/{total}", flush=True)
            short = h["name"].replace("npc_dota_hero_", "")
            d = icons / short
            if d.exists() and any(d.glob("*.png")):
                skip += 1
                continue
            d.mkdir(parents=True, exist_ok=True)
            try:
                r = c.get(f"{CDN}/{short}.png")
                if r.status_code == 200 and r.content[:4] == b"\x89PNG":
                    (d / f"{short}.png").write_bytes(r.content)
                    ok += 1
                else:
                    fail += 1
                    print(f"  {short}: HTTP {r.status_code}", flush=True)
            except Exception as e:
                fail += 1
                print(f"  {short}: {e}", flush=True)
            time.sleep(0.15)
    print(f"icons: {ok} скачано, {skip} уже было, {fail} ошибок -> {icons}")


if __name__ == "__main__":
    main()
