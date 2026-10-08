"""Full release pipeline: PyInstaller exe -> Inno Setup installer.

Run on Windows:
  pip install -r requirements.txt pyinstaller
  python scripts/build_release.py

Requires Inno Setup 6 installed (iscc on PATH or default location).
Output: installer/Output/DotaAssist-Setup.exe
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def find_iscc() -> str | None:
    for cand in (
        shutil.which("iscc"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ):
        if cand and Path(cand).exists():
            return cand
    return None


def git_version() -> str:
    try:
        return subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=ROOT, text=True).strip().lstrip("v")
    except Exception:
        return "0.0.0"


def main():
    # 1. exe
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build.py")],
                   check=True)

    # 2. installer — версия из git-тега (iscc /D переопределяет #define)
    iscc = find_iscc()
    if not iscc:
        sys.exit("Inno Setup не найден — поставь https://jrsoftware.org/isinfo.php "
                 "и перезапусти")
    iss = ROOT / "installer" / "DotaAssist.iss"
    subprocess.run([iscc, f"/DAppVersion={git_version()}", str(iss)],
                   cwd=ROOT, check=True)
    print("\nГотово: installer\\Output\\DotaAssist-Setup.exe")


if __name__ == "__main__":
    main()
