"""Show or hide only the managed Godot process's main window."""

import ctypes
from ctypes import wintypes
import os


def game_window(pid, show=False, background=False):
    if os.name != "nt":
        return False
    ui = ctypes.windll.user32
    found = []
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    ui.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    ui.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    for name in ("IsIconic", "SetForegroundWindow", "IsWindowVisible"):
        getattr(ui, name).argtypes = [wintypes.HWND]
    ui.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]

    @callback
    def visit(hwnd, unused):
        owner = wintypes.DWORD()
        ui.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            name = ctypes.create_unicode_buffer(128)
            ui.GetClassNameW(hwnd, name, len(name))
            if name.value.startswith("Engine"):
                found.append(hwnd)
                return False
        return True

    ui.EnumWindows(visit, 0)
    if not found:
        return False
    hwnd = found[0]
    if show:
        ui.ShowWindowAsync(hwnd, 9)
        ui.SetForegroundWindow(hwnd)
    elif (background or ui.IsIconic(hwnd)) and ui.IsWindowVisible(hwnd):
        ui.ShowWindowAsync(hwnd, 0)
    return True
