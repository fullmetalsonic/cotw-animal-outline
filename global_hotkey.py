"""User-selected whole-mod toggle; no key or mouse injection."""
import ctypes as C
from ctypes import wintypes as W
import queue
import threading

HOTKEY_ID, HOTKEY_MODIFIERS, HOTKEY_VK = 0x4354, 0x4006, 0x79
HOTKEY_LABEL = "Ctrl+Shift+F10"
WM_HOTKEY, WM_QUIT = 0x312, 0x12


class GlobalHotkey(threading.Thread):
    def __init__(self, *, user32=None, kernel32=None):
        super().__init__(daemon=True)
        self.u = user32 if user32 is not None else C.WinDLL("user32",use_last_error=True)
        self.k = kernel32 if kernel32 is not None else C.WinDLL("kernel32",use_last_error=True)
        self.events = queue.Queue()
        self.stopping = threading.Event()
        self.thread_id = None
        declarations = {
            "RegisterHotKey": ([W.HWND,C.c_int,W.UINT,W.UINT],W.BOOL),
            "UnregisterHotKey": ([W.HWND,C.c_int],W.BOOL),
            "GetMessageW": ([C.POINTER(W.MSG),W.HWND,W.UINT,W.UINT],C.c_int),
            "PostThreadMessageW": ([W.DWORD,W.UINT,W.WPARAM,W.LPARAM],W.BOOL),
        }
        if user32 is None:
            for name,(args,ret) in declarations.items():
                fn=getattr(self.u,name)
                fn.argtypes,fn.restype=args,ret
        if kernel32 is None:
            self.k.GetCurrentThreadId.argtypes=[]
            self.k.GetCurrentThreadId.restype=W.DWORD

    def run(self):
        registered=False
        try:
            self.thread_id=self.k.GetCurrentThreadId()
            registered=bool(self.u.RegisterHotKey(None,HOTKEY_ID,HOTKEY_MODIFIERS,HOTKEY_VK))
            if not registered:
                self.events.put(("unavailable",C.get_last_error()))
                return
            self.events.put(("ready",HOTKEY_LABEL))
            if self.stopping.is_set():
                return
            msg=W.MSG()
            while True:
                result=self.u.GetMessageW(C.byref(msg),None,0,0)
                if result==0:
                    break
                if result<0:
                    self.events.put(("unavailable",C.get_last_error()))
                    break
                if self.stopping.is_set():
                    break
                if msg.message==WM_HOTKEY and msg.wParam==HOTKEY_ID:
                    self.events.put(("toggle",None))
        finally:
            if registered:
                self.u.UnregisterHotKey(None,HOTKEY_ID)

    def close(self):
        self.stopping.set()
        if self.thread_id is not None:
            self.u.PostThreadMessageW(self.thread_id,WM_QUIT,0,0)
