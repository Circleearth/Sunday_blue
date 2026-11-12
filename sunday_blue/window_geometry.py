"""Screen work-area geometry for the existing frameless Widgets shell."""
import sys
from PySide6.QtCore import QRect

def initial_rect(available):
    w=min(1440,max(1,round(available.width()*.94)));h=min(900,max(1,round(available.height()*.92)))
    return QRect(available.x()+(available.width()-w)//2,available.y()+(available.height()-h)//2,w,h)

def constrain_maximize(message,minimum=None,scale=1):
    if sys.platform!='win32':return False
    import ctypes
    from ctypes import wintypes
    msg=wintypes.MSG.from_address(int(message))
    if msg.message!=0x24:return False # WM_GETMINMAXINFO; physical pixels from the same monitor
    class MINMAXINFO(ctypes.Structure):
        _fields_=[('reserved',wintypes.POINT),('maxSize',wintypes.POINT),('maxPosition',wintypes.POINT),('minTrack',wintypes.POINT),('maxTrack',wintypes.POINT)]
    class MONITORINFO(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('monitor',wintypes.RECT),('work',wintypes.RECT),('flags',wintypes.DWORD)]
    user=ctypes.windll.user32;user.MonitorFromWindow.argtypes=[wintypes.HWND,wintypes.DWORD];user.MonitorFromWindow.restype=wintypes.HANDLE
    user.GetMonitorInfoW.argtypes=[wintypes.HANDLE,ctypes.POINTER(MONITORINFO)]
    monitor=user.MonitorFromWindow(msg.hWnd,2);info=MONITORINFO();info.size=ctypes.sizeof(info)
    if not user.GetMonitorInfoW(monitor,ctypes.byref(info)):return False
    bounds=MINMAXINFO.from_address(msg.lParam);bounds.maxPosition.x=info.work.left-info.monitor.left;bounds.maxPosition.y=info.work.top-info.monitor.top
    bounds.maxSize.x=info.work.right-info.work.left;bounds.maxSize.y=info.work.bottom-info.work.top
    if minimum is not None:
        bounds.minTrack.x=min(bounds.maxSize.x,round(minimum.width()*scale));bounds.minTrack.y=min(bounds.maxSize.y,round(minimum.height()*scale))
    return True
