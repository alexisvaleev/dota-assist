"""Extract every hero pick-screen icon variant from pak01_dir.vpk —
including arcana/persona variants — into data/icons/<hero_name>/.

Windows-only. Uses ValveResourceFormat (VRF) CLI to decompile vtex_c
files. Download VRF from github.com/ValveResourceFormat/ValveResourceFormat
releases (Source2Viewer-CLI) and point VRF_CLI at the binary in config.json
or here.

Run:  python scripts/extract_icons.py
"""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

DOTA = Path(CFG["dota_path"])
VPK = DOTA / "game" / "dota" / "pak01_dir.vpk"
# Icons used by the pick grid / team panels live under:
VPK_ICON_DIRS = ["panorama/images/heroes/", "panorama/images/heroes/selection/"]

VRF_CLI = CFG.get("vrf_cli", "Source2Viewer-CLI.exe")


def main():
    if not VPK.exists():
        raise SystemExit(f"pak01_dir.vpk не найден: {VPK} — проверь dota_path в config.json")
    out = ROOT / "data" / "icons"
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        for d in VPK_ICON_DIRS:
            # Decompile whole subtree: produces PNGs for every vtex_c image.
            subprocess.run(
                [VRF_CLI, "-i", str(VPK), "-o", tmp, "-e", "vtex_c",
                 "-d", d, "--recursive"],
                check=False)
        # Re-layout: tmp/**/xxx.png -> data/icons/<hero>/xxx.png
        # Hero icon names: <hero>[_persona|_arcana...].png; base dir holds
        # selection variants.
        n = 0
        for png in Path(tmp).rglob("*.png"):
            stem = png.stem.split("_alt")[0]
            # hero name is the filename up to first persona/arcana marker —
            # VPK layout already groups variants under per-hero dirs in
            # selection/, so prefer the parent dir name when present.
            hero_dir = png.parent.name if png.parent.name != "heroes" else stem
            dest_dir = out / hero_dir
            dest_dir.mkdir(exist_ok=True)
            shutil.copy2(png, dest_dir / png.name)
            n += 1
    print(f"extracted {n} icons -> {out}")
    print("Проверь: если <hero>-папок мало — посмотри реальную структуру "
          "tmp и поправь группировку под текущий VPK.")


if __name__ == "__main__":
    main()
