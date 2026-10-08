"""Автообновление из GitHub Releases.

check: GET releases/latest -> сравнить тег с текущей версией.
apply: скачать DotaAssist.exe -> cmd-скрипт ждёт выхода процесса,
       подменяет exe и перезапускает. Установленная копия живёт в
       %LOCALAPPDATA%\\Programs (PrivilegesRequired=lowest) — права не нужны.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Callable

import httpx

from version import current as current_version

REPO = "alexisvaleev/dota-assist"
API = f"https://api.github.com/repos/{REPO}/releases/latest"


def _ver(tag: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in tag.lstrip("vV").split("."))
    except ValueError:
        return (0,)


def check() -> dict | None:
    """-> {"tag", "url", "size"} если есть новее, иначе None."""
    try:
        r = httpx.get(API, timeout=15,
                      headers={"Accept": "application/vnd.github+json"})
        if r.status_code != 200:
            return None
        rel = r.json()
        tag = rel.get("tag_name", "")
        cur = current_version()
        if cur == "dev" or _ver(tag) <= _ver(cur):
            return None
        asset = next((a for a in rel.get("assets", [])
                      if a["name"] == "DotaAssist.exe"), None)
        if not asset:
            return None
        return {"tag": tag, "url": asset["browser_download_url"],
                "size": asset.get("size", 0)}
    except Exception:
        return None


def apply_update(url: str, status_cb: Callable[[str], None] | None = None):
    """Качает новый exe и запускает подменяющий cmd. Приложение должно
    завершиться сразу после вызова (вызывающий делает app.quit/exit)."""
    if not getattr(sys, "frozen", False):
        if status_cb:
            status_cb("обновление только для exe-сборки")
        return False
    exe = Path(sys.executable)
    new = exe.with_name("DotaAssist.new.exe")
    try:
        if status_cb:
            status_cb("скачиваю обновление…")
        with httpx.stream("GET", url, timeout=120,
                          follow_redirects=True) as r:
            r.raise_for_status()
            with new.open("wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
    except Exception as e:
        if status_cb:
            status_cb(f"обновление не скачалось: {e}")
        return False

    bat = Path(tempfile.gettempdir()) / "dotaassist_update.cmd"
    bat.write_text(
        "@echo off\r\n"
        "ping -n 3 127.0.0.1 >nul\r\n"
        f'move /y "{new}" "{exe}" >nul\r\n'
        f'start "" "{exe}"\r\n'
        'del "%~f0"\r\n',
        encoding="ascii")
    subprocess.Popen(["cmd", "/c", str(bat)],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return True


def check_async(on_result: Callable[[dict | None], None]):
    t = threading.Thread(target=lambda: on_result(check()),
                         daemon=True, name="updater")
    t.start()
    return t
