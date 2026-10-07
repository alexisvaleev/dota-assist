"""Сборка single-file exe через PyInstaller (запускать на Windows).

  pip install pyinstaller
  python scripts/build.py

Бандлим только наш код и app/calibration.json + data/items.json
(ручные правила). config.json и иконки НЕ зашиваются:
  - config.json живёт в %APPDATA%\\DotaAssist (токен не утекает с exe);
  - иконки героев — ассеты Valve, извлекаются на машине пользователя
    (scripts/extract_icons.py) в %APPDATA%\\DotaAssist\\data\\icons.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    sep = ";" if sys.platform == "win32" else ":"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--windowed", "--clean",
        "--name", "DotaAssist",
        "--add-data", f"app/calibration.json{sep}app",
        "--add-data", f"data/items.json{sep}data",
        "--add-data", f"config.example.json{sep}.",
        "--paths", str(ROOT / "app"),
        str(ROOT / "app" / "main.py"),
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)
    print("\nГотово: dist/DotaAssist.exe")
    print("При первом запуске: python -m scripts.first_run "
          "(или скачай данные и иконки вручную)")


if __name__ == "__main__":
    main()
