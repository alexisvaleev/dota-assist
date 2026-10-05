"""Resource path resolution: user-editable copy next to the exe wins,
bundled (PyInstaller _MEIPASS / source tree) is the fallback.

  config.json, app/calibration.json, data/** — all overridable.
"""
import sys
from pathlib import Path

# bundled resources root (inside exe: _MEIPASS; from source: repo root)
if getattr(sys, "frozen", False):
    BUNDLED = Path(sys._MEIPASS)
    EXTERNAL = Path(sys.executable).parent      # next to DotaAssist.exe
else:
    BUNDLED = Path(__file__).resolve().parent.parent
    EXTERNAL = BUNDLED


def resource(rel: str) -> Path:
    ext = EXTERNAL / rel
    return ext if ext.exists() else BUNDLED / rel


def resource_dir(rel: str) -> Path:
    """Directory version: external if it exists, else bundled."""
    ext = EXTERNAL / rel
    return ext if ext.is_dir() else BUNDLED / rel
