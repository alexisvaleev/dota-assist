"""Автообновление из GitHub Releases.

check: GET releases/latest -> сравнить тег с текущей версией, заодно
       находим checksums.txt среди ассетов того же релиза.
apply: скачать DotaAssist.exe -> проверить размер и sha256 по
       checksums.txt -> cmd-скрипт ждёт выхода процесса (ретраи ~30с),
       подменяет exe и перезапускает. Установленная копия живёт в
       %LOCALAPPDATA%\\Programs (PrivilegesRequired=lowest) — права не нужны.
Qt здесь нет: функции вызываются из воркер-потоков, выход из приложения
делает вызывающий (в GUI-потоке, через сигнал).
"""
from __future__ import annotations

import hashlib
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
EXE_NAME = "DotaAssist.exe"


def _ver(tag: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in tag.lstrip("vV").split("."))
    except ValueError:
        return (0,)


def _say(cb: Callable[[str], None] | None, msg: str):
    if cb:
        cb(msg)


def _parse_checksums(text: str, name: str) -> str | None:
    """Строки '<sha256>  <file>' -> хэш для name (None, если нет)."""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and Path(parts[1].lstrip("*")).name == name:
            return parts[0].lower()
    return None


def _verify(path: Path, expected_size: int = 0,
            sha256_hex: str = "") -> str | None:
    """-> None, если файл прошёл проверку, иначе текст ошибки."""
    try:
        size = path.stat().st_size
    except OSError as e:
        return f"нет файла: {e}"
    if expected_size and size != expected_size:
        return f"размер {size} != ожидаемого {expected_size}"
    if not sha256_hex:
        return "нет sha256 для файла в checksums.txt"
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != sha256_hex.lower():
        return "sha256 не совпал"
    return None


def check() -> dict | None:
    """-> {"tag", "url", "size", "checksums_url"} если есть новее, иначе None."""
    cur = current_version()
    if cur == "dev":                    # dev-сборка: не дёргаем GitHub
        return None
    try:
        r = httpx.get(API, timeout=15,
                      headers={"Accept": "application/vnd.github+json"})
        if r.status_code != 200:
            return None
        rel = r.json()
        tag = rel.get("tag_name", "")
        if _ver(tag) <= _ver(cur):
            return None
        assets = {a.get("name"): a for a in rel.get("assets", [])}
        exe = assets.get(EXE_NAME)
        if not exe:
            return None
        info = {"tag": tag, "url": exe["browser_download_url"],
                "size": exe.get("size", 0)}
        sums = assets.get("checksums.txt")
        if sums:
            info["checksums_url"] = sums["browser_download_url"]
        return info
    except Exception:
        return None


def apply_update(url, status_cb: Callable[[str], None] | None = None) -> bool:
    """Готовит подмену exe: качает, проверяет по checksums.txt релиза,
    пишет cmd-скрипт и запускает его. url — строка или dict из check()
    (нужны url/size/checksums_url). True = всё готово, вызывающий
    завершает приложение сам; скачанный exe не подменится, пока живы."""
    if not getattr(sys, "frozen", False):
        _say(status_cb, "обновление только для exe-сборки")
        return False
    info = url if isinstance(url, dict) else {"url": url}
    exe = Path(sys.executable)
    new = exe.with_name("DotaAssist.new.exe")
    try:
        _say(status_cb, "скачиваю обновление…")
        with httpx.stream("GET", info.get("url", ""), timeout=120,
                          follow_redirects=True) as r:
            r.raise_for_status()
            with new.open("wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
    except Exception as e:
        _say(status_cb, f"обновление не скачалось: {e}")
        return False

    # целостность: sha256 из checksums.txt того же релиза
    sums_url = info.get("checksums_url")
    if not sums_url:
        new.unlink(missing_ok=True)
        _say(status_cb, "в релизе нет checksums.txt — обновление отменено")
        return False
    try:
        txt = httpx.get(sums_url, timeout=30, follow_redirects=True).text
        err = _verify(new, info.get("size", 0),
                      _parse_checksums(txt, EXE_NAME) or "")
    except Exception as e:
        err = f"checksums.txt не скачался: {e}"
    if err:
        new.unlink(missing_ok=True)
        _say(status_cb, f"обновление отменено: {err}")
        return False

    # скрипт: ждём выхода процесса и ретраим move до ~30с, потом рестарт
    bat = Path(tempfile.gettempdir()) / "dotaassist_update.cmd"
    try:
        bat.write_text(
            "@echo off\r\n"
            "set /a tries=0\r\n"
            ":retry\r\n"
            f'move /y "{new}" "{exe}" >nul 2>&1\r\n'
            f'if not exist "{new}" goto moved\r\n'
            "set /a tries+=1\r\n"
            "if %tries% geq 30 goto end\r\n"
            "ping -n 2 127.0.0.1 >nul\r\n"
            "goto retry\r\n"
            ":moved\r\n"
            f'start "" "{exe}"\r\n'
            ":end\r\n"
            'del "%~f0"\r\n',
            encoding="ascii")
    except Exception as e:
        _say(status_cb, f"не смог записать скрипт обновления: {e}")
        return False
    subprocess.Popen(["cmd", "/c", str(bat)],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return True


def check_async(on_result: Callable[[dict | None], None]):
    t = threading.Thread(target=lambda: on_result(check()),
                         daemon=True, name="updater")
    t.start()
    return t
