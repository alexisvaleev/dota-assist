"""Окно Dota 2 → клиентская область и монитор (Windows, чистый ctypes).

Зачем: авто-определение монитора и смещения игровой области, чтобы
калибровка не зависела от monitors[0] и ручного выбора монитора.
"""
import sys
import ctypes
from ctypes import wintypes


def dota_client_rect() -> tuple[int, int, int, int] | None:
    """(x, y, w, h) клиентской области окна Dota в координатах виртуального
    экрана. None — не Windows или окно не найдено."""
    if sys.platform != "win32":
        return None
    u = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lp):
        if not u.IsWindowVisible(hwnd):
            return True
        n = u.GetWindowTextLengthW(hwnd)
        if not n:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hwnd, buf, n + 1)
        if "dota 2" in buf.value.lower():
            found.append(hwnd)
        return True

    u.EnumWindows(cb, 0)
    if not found:
        return None
    hwnd = found[0]
    rc = wintypes.RECT()
    u.GetClientRect(hwnd, ctypes.byref(rc))
    pt = wintypes.POINT(0, 0)
    u.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y, rc.right - rc.left, rc.bottom - rc.top


def monitor_index_for(x: int, y: int, monitors: list[dict]) -> int:
    """Индекс монитора mss (1..N), содержащего точку (x, y) в координатах
    виртуального экрана. monitors = sct.monitors."""
    for i, m in enumerate(monitors):
        if i == 0:
            continue                      # monitors[0] — объединённый экран
        if m["left"] <= x < m["left"] + m["width"] \
                and m["top"] <= y < m["top"] + m["height"]:
            return i
    return 1 if len(monitors) > 1 else 0
