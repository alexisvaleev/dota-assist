"""Разрешение путей ресурсов.

Порядок поиска файлов/папок:
  1. user_dir()   — %APPDATA%\\DotaAssist (Windows) / ~/.local/share/dota-assist;
                    туда fetch_data складывает кэш и extract_icons — иконки.
                    В режиме разработки (не frozen) user_dir == корень репо.
  2. EXTERNAL     — файлы рядом с exe (ручные переопределения).
  3. BUNDLED      — ресурсы, зашитые в exe (PyInstaller _MEIPASS) или репо.

Секреты (config.json с токеном) в exe НЕ зашиваются: frozen-режим читает
config.json только из user_dir/EXTERNAL.
"""
import os
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    BUNDLED = Path(sys._MEIPASS)
    EXTERNAL = Path(sys.executable).parent      # рядом с DotaAssist.exe
else:
    BUNDLED = Path(__file__).resolve().parent.parent
    EXTERNAL = BUNDLED


def user_dir() -> Path:
    if FROZEN:
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "DotaAssist"
    if os.environ.get("DOTA_ASSIST_HOME"):
        return Path(os.environ["DOTA_ASSIST_HOME"])
    return EXTERNAL                             # dev: репо


def layered_file(rel: str) -> Path:
    """Первый существующий файл в user_dir → EXTERNAL → BUNDLED."""
    for base in (user_dir(), EXTERNAL, BUNDLED):
        p = base / rel
        if p.is_file():
            return p
    return EXTERNAL / rel


def layered_dir(rel: str) -> Path:
    for base in (user_dir(), EXTERNAL, BUNDLED):
        p = base / rel
        if p.is_dir():
            return p
    return EXTERNAL / rel


# обратная совместимость
resource = layered_file
resource_dir = layered_dir


def config_file() -> Path:
    """config.json: секреты живут в user_dir/рядом с exe, не в exe."""
    for base in (user_dir(), EXTERNAL):
        p = base / "config.json"
        if p.is_file():
            return p
    p = user_dir() / "config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p                                  # создать при первом запуске
