"""Build a single-file Windows exe via PyInstaller.

Run on Windows inside the venv:
  pip install pyinstaller
  python scripts/build.py

Output: dist/DotaAssist.exe — bundles app/, data/ and config.json
(config.json is embedded at build time; do NOT share the exe publicly
as it contains your STRATZ token).
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
        "--add-data", f"data{sep}data",
        "--add-data", f"config.json{sep}.",
        "--add-data", f"app/calibration.json{sep}app",
        "--paths", str(ROOT / "app"),
        str(ROOT / "app" / "main.py"),
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)
    print("\nГотово: dist/DotaAssist.exe")
    print("⚠ exe содержит твой STRATZ токен — не публикуй бинарь")


if __name__ == "__main__":
    main()
