"""Первый запуск после установки: качает данные и иконки в %APPDATA%.

  python scripts/first_run.py        (или first_run.exe после сборки)

Что делает:
  1. Создаёт %APPDATA%\\DotaAssist\\config.json из дефолтов, если нет.
  2. fetch_data.py -> %APPDATA%\\DotaAssist\\data\\*.json
  3. extract_icons.py -> %APPDATA%\\DotaAssist\\data\\icons\\*
     (требуется dota_path в config.json и Source2Viewer-CLI)
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from paths import user_dir, layered_file  # noqa: E402


def ensure_config():
    p = user_dir() / "config.json"
    if p.exists():
        return p
    p.parent.mkdir(parents=True, exist_ok=True)
    ex = layered_file("config.example.json")
    cfg = json.loads(ex.read_text(encoding="utf-8")) if ex.exists() else {}
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    print(f"создан {p} — впиши stratz_token / account_id при желании")
    return p


def main():
    cfg = ensure_config()
    print(f"конфиг: {cfg}\n")

    print("1/2  данные OpenDota/STRATZ…")
    subprocess.run([sys.executable,
                    str(ROOT / "scripts" / "fetch_data.py")], check=False)

    print("2/2  иконки героев из VPK…")
    try:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "extract_icons.py")],
            check=True)
    except Exception as e:
        print(f"  пропущено: {e}\n"
              "  позже: python scripts/extract_icons.py "
              "(нужен Source2Viewer-CLI)")

    print("\nГотово. Запусти DotaAssist.exe; Dota должна быть в "
          "Borderless Windowed.")


if __name__ == "__main__":
    main()
