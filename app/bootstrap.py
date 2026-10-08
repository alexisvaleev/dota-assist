"""Первый запуск замороженного exe: если данных нет — качаем сами.

Plug&play: пользователь ставит DotaAssist-Setup.exe, запускает — и при
пустом или протухшем кэше приложение само тянет data/*.json и CDN-иконки в
%APPDATA%\\DotaAssist\\data. Прогресс уходит в оверлей через status_cb.

Свежесть: data/_meta.json {"fetched_at": epoch} — маркер, который
fetch_data пишет в конце удачной загрузки; у кэшей старых версий читаем
_meta.fetched_at внутри heroes.json/meta.json. Данные старше
REFRESH_DAYS суток перекачиваются при запуске. Иконки докачиваются, если
в data/icons меньше ICON_MIN_HEROES папок героев — прошлый прогон,
видимо, оборвался или был пропущен.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable

from paths import layered_dir, user_dir

REFRESH_DAYS = 2        # данные старше — перекачиваем при запуске
ICON_MIN_HEROES = 100   # меньше папок в data/icons — иконки не докачаны
_META_FILE = "_meta.json"
_CORE = ("heroes.json", "meta.json")


def _data_dirs() -> list[Path]:
    """Слои, где может лежать кэш: user_dir в приоритете."""
    return [user_dir() / "data", layered_dir("data")]


def _has_core(d: Path) -> bool:
    return all((d / name).exists() for name in _CORE)


def data_ready(data_dir: Path | None = None) -> bool:
    """Минимум для работы: heroes.json + meta.json где-то по слоям."""
    dirs = [data_dir] if data_dir is not None else _data_dirs()
    return any(_has_core(d) for d in dirs)


def _parse_ts(v) -> float | None:
    """fetched_at -> epoch: число либо ISO 'YYYY-MM-DDTHH:MM:SS'
    (локальное время — так пишет engine.dataload.now_iso)."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            pass
        try:
            from datetime import datetime
            return datetime.fromisoformat(v).timestamp()
        except ValueError:
            return None
    return None


def read_fetched_at(data_dir: Path) -> float | None:
    """epoch последней загрузки в data_dir; None — метки нет или битая.

    Сначала маркер _meta.json, затем _meta.fetched_at внутри
    heroes.json/meta.json — так выглядят кэши, записанные до появления
    маркера. Берём минимум: кэш свеж настолько, насколько свеж его
    самый старый файл ядра.
    """
    try:
        p = data_dir / _META_FILE
        if p.is_file():
            ts = _parse_ts(
                json.loads(p.read_text(encoding="utf-8")).get("fetched_at"))
            if ts is not None:
                return ts
    except Exception:
        pass
    stamps = []
    for name in _CORE:
        try:
            raw = json.loads((data_dir / name).read_text(encoding="utf-8"))
        except Exception:
            continue
        ts = _parse_ts((raw.get("_meta") or {}).get("fetched_at"))
        if ts is not None:
            stamps.append(ts)
    return min(stamps) if stamps else None


def _is_fresh(data_dir: Path, now: float | None = None) -> bool:
    """Ядро данных на месте и fetched_at моложе REFRESH_DAYS."""
    if not _has_core(data_dir):
        return False
    ts = read_fetched_at(data_dir)
    if ts is None:
        return False
    now = time.time() if now is None else now
    return now - ts < REFRESH_DAYS * 86400


def data_fresh(now: float | None = None) -> bool:
    """Свежие (моложе REFRESH_DAYS) данные есть хотя бы в одном слое."""
    return any(_is_fresh(d, now) for d in _data_dirs())


def icons_ready(icons_dir: Path | None = None) -> bool:
    """data/icons цел: >= ICON_MIN_HEROES папок героев с png внутри.

    Пустые папки не считаем: fetch_icons их так и так перекачает.
    Меньше порога — прошлая загрузка оборвалась/была пропущена.
    """
    d = icons_dir if icons_dir is not None else layered_dir("data/icons")
    try:
        n = sum(1 for p in d.iterdir()
                if p.is_dir() and any(p.glob("*.png")))
        return n >= ICON_MIN_HEROES
    except OSError:
        return False


def bootstrap(status_cb: Callable[[str], None] | None = None,
              on_done: Callable[[], None] | None = None):
    """Качает данные (нет или протухли) и иконки (не докачаны).
    Запускать в треде — сеть блокирующая."""
    def say(msg: str):
        print(f"[bootstrap] {msg}")
        if status_cb:
            status_cb(msg)

    fresh = data_fresh()
    if fresh and icons_ready():
        if on_done:
            on_done()
        return

    if not fresh:
        say("Первый запуск: скачиваю данные…" if not data_ready()
            else "Данные устарели — обновляю…")
        try:
            import fetch_data
            fetch_data.main([])
        except Exception as e:
            say(f"данные: ошибка ({e}) — повторится при следующем запуске")
            if not data_ready():
                return          # кэша нет совсем — дальше бессмысленно
            # иначе живём на старом кэше — иконки всё равно проверим
        else:
            say("Данные обновлены")

    if not icons_ready():
        try:
            import fetch_icons
            say("Качаю иконки героев…")
            fetch_icons.main()      # sys.exit, если heroes.json так и нет
        except (Exception, SystemExit) as e:
            say(f"иконки: {e} (не критично)")

    say("Готово")
    if on_done:
        on_done()


def bootstrap_async(status_cb: Callable[[str], None] | None = None,
                    on_done: Callable[[], None] | None = None):
    t = threading.Thread(
        target=bootstrap, kwargs={"status_cb": status_cb, "on_done": on_done},
        daemon=True, name="bootstrap")
    t.start()
    return t
