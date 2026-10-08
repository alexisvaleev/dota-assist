"""Версия приложения.

При сборке PyInstaller вкладывает version.txt (git describe --tags),
при запуске из исходников — "dev".
"""
from paths import layered_file


def current() -> str:
    p = layered_file("version.txt")
    if p.exists():
        return p.read_text(encoding="utf-8").strip().lstrip("v")
    return "dev"
