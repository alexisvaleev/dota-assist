"""Извлекает иконки героев (все варианты аркан/персон) из pak01_dir.vpk
в <user_dir>/data/icons/<hero_name>/.

Windows-only. Использует Source2Viewer-CLI (ValveResourceFormat):
github.com/ValveResourceFormat/ValveResourceFormat/releases —
путь в config.json -> "vrf_cli" или рядом в PATH.

Иконки — ассеты Valve: живут только локально, в exe/репо не попадают.

Run:  python scripts/extract_icons.py
"""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT / "app"))
from paths import user_dir, layered_file  # noqa: E402

CFG = json.loads(layered_file("config.json").read_text(encoding="utf-8"))

DOTA = Path(CFG["dota_path"])
VPK = DOTA / "game" / "dota" / "pak01_dir.vpk"
VPK_ICON_DIRS = ["panorama/images/heroes/", "panorama/images/heroes/selection/"]

VRF_CLI = CFG.get("vrf_cli", "Source2Viewer-CLI.exe")


def main():
    if not VPK.exists():
        raise SystemExit(
            f"pak01_dir.vpk не найден: {VPK} — проверь dota_path в config.json")
    out = user_dir() / "data" / "icons"
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        for d in VPK_ICON_DIRS:
            subprocess.run(
                [VRF_CLI, "-i", str(VPK), "-o", tmp, "-e", "vtex_c",
                 "-d", d, "--recursive"],
                check=False)
        n = 0
        for png in Path(tmp).rglob("*.png"):
            stem = png.stem.split("_alt")[0]
            hero_dir = png.parent.name if png.parent.name != "heroes" else stem
            dest_dir = out / hero_dir
            dest_dir.mkdir(exist_ok=True)
            shutil.copy2(png, dest_dir / png.name)
            n += 1
    print(f"extracted {n} icons -> {out}")
    print("Проверь: если папок мало — структура VPK могла измениться, "
          "посмотри tmp и поправь группировку.")


if __name__ == "__main__":
    main()
