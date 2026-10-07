"""Разработческий сетап: GSI cfg + данные + иконки. Один раз после клона.

  python scripts/setup.py            # все шаги
  python scripts/setup.py --gsi-only # только конфиг GSI
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from paths import layered_file  # noqa: E402

CFG = {}
for p in (ROOT / "config.json", layered_file("config.example.json")):
    if Path(p).exists():
        CFG = json.loads(Path(p).read_text(encoding="utf-8"))
        break


def install_gsi():
    src = ROOT / "gsi" / "gamestate_integration_dotaassist.cfg"
    dst_dir = (Path(CFG["dota_path"]) / "game" / "dota" / "cfg"
               / "gamestate_integration")
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst_dir / src.name)
    print(f"[gsi] cfg -> {dst_dir}")
    print("[gsi] добавь -gamestateintegration в параметры запуска Dota")


def fetch():
    print("[data] загрузка OpenDota/STRATZ ->", end=" ")
    from paths import user_dir
    print(user_dir() / "data")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "fetch_data.py")],
                   check=True)


def icons():
    try:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "extract_icons.py")],
            check=True)
    except Exception as e:
        print(f"[icons] пропущено: {e}\n"
              "        скачай Source2Viewer-CLI и повтори "
              "scripts/extract_icons.py")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gsi-only", action="store_true")
    args = ap.parse_args()

    install_gsi()
    if args.gsi_only:
        return
    fetch()
    icons()
    print("\nОсталось вручную: откалибровать app/calibration.json "
          "по скриншоту драфта (scripts/screenshot_for_calib.py)")


if __name__ == "__main__":
    main()
