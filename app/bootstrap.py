"""Первый запуск замороженного exe: если данных нет — качаем сами.

Plug&play: пользователь ставит DotaAssist-Setup.exe, запускает — и при
пустом кэше приложение само тянет data/*.json и CDN-иконки в
%APPDATA%\\DotaAssist\\data. Прогресс уходит в оверлей через status_cb.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from paths import layered_dir, user_dir


def data_ready(data_dir: Path | None = None) -> bool:
    """Минимум для работы: heroes.json + meta.json где-то по слоям."""
    dirs = [user_dir() / "data", layered_dir("data")]
    for d in dirs:
        if (d / "heroes.json").exists() and (d / "meta.json").exists():
            return True
    return False


def bootstrap(status_cb: Callable[[str], None] | None = None,
              on_done: Callable[[], None] | None = None):
    """Скачивает данные и иконки, если их ещё нет. Запускать в треде."""
    def say(msg: str):
        print(f"[bootstrap] {msg}")
        if status_cb:
            status_cb(msg)

    if data_ready():
        if on_done:
            on_done()
        return
    say("Первый запуск: скачиваю данные…")

    try:
        import fetch_data
        fetch_data.main([])
    except Exception as e:
        say(f"данные: ошибка ({e}) — повторится при следующем запуске")
        return

    try:
        import fetch_icons
        say("Качаю иконки героев…")
        fetch_icons.main()
    except Exception as e:
        say(f"иконки: {e} (не критично)")

    say("Данные загружены")
    if on_done:
        on_done()


def bootstrap_async(status_cb: Callable[[str], None] | None = None,
                    on_done: Callable[[], None] | None = None):
    t = threading.Thread(
        target=bootstrap, kwargs={"status_cb": status_cb, "on_done": on_done},
        daemon=True, name="bootstrap")
    t.start()
    return t
