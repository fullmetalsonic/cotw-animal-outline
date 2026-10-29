"""Shared Windows process boundary for the two temporary game modes."""
from contextlib import contextmanager
import ctypes as C
from ctypes import wintypes as W
import struct

import game_memory as probe

ALLOCATION_SIZE = 0x22000


def rel_call(source, target):
    delta = target - (source + 5)
    if not -(1 << 31) <= delta < (1 << 31):
        raise ValueError("게임 모드이 호출 범위를 벗어났습니다")
    return b"\xe8" + struct.pack("<i", delta)



class ThreadEntry(C.Structure):
    _fields_ = [("size", W.DWORD), ("usage", W.DWORD), ("tid", W.DWORD),
                ("pid", W.DWORD), ("priority", W.LONG), ("delta", W.LONG), ("flags", W.DWORD)]



class NativeAPI:
    """Narrow Windows boundary, replaceable by a fake for all offline tests."""
    def __init__(self, game, writer):
        self.game, self.writer, self.k = game, writer, probe.K
        k = self.k
        declarations = {
            "VirtualAllocEx": ([W.HANDLE, C.c_void_p, C.c_size_t, W.DWORD, W.DWORD], C.c_void_p),
            "VirtualProtectEx": ([W.HANDLE, C.c_void_p, C.c_size_t, W.DWORD, C.POINTER(W.DWORD)], W.BOOL),
            "FlushInstructionCache": ([W.HANDLE, C.c_void_p, C.c_size_t], W.BOOL),
            "WriteProcessMemory": ([W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)], W.BOOL),
            "Thread32First": ([W.HANDLE, C.POINTER(ThreadEntry)], W.BOOL),
            "Thread32Next": ([W.HANDLE, C.POINTER(ThreadEntry)], W.BOOL),
            "OpenThread": ([W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            "SuspendThread": ([W.HANDLE], W.DWORD), "ResumeThread": ([W.HANDLE], W.DWORD),
            "GetThreadContext": ([W.HANDLE, C.c_void_p], W.BOOL),
            "GetProcessIdOfThread": ([W.HANDLE], W.DWORD),
            "GetExitCodeProcess": ([W.HANDLE, C.POINTER(W.DWORD)], W.BOOL),
            "QueryPerformanceCounter": ([C.POINTER(C.c_longlong)], W.BOOL),
            "QueryPerformanceFrequency": ([C.POINTER(C.c_longlong)], W.BOOL),
        }
        for name, (args, result) in declarations.items():
            fn = getattr(k, name); fn.argtypes, fn.restype = args, result

    def read(self, address, size):
        return self.game.read(address, size)

    def write(self, address, payload):
        if not 0x10000 <= address <= 0x7FFFFFFFFFFF - len(payload) or not 0 < len(payload) <= ALLOCATION_SIZE:
            raise ValueError("게임 모드 쓰기 범위가 잘못되었습니다")
        buffer = C.create_string_buffer(payload, len(payload)); count = C.c_size_t()
        if not self.k.WriteProcessMemory(self.writer, C.c_void_p(address), buffer, len(payload), C.byref(count)) or count.value != len(payload):
            raise OSError("게임 모드 메모리 쓰기에 실패했습니다")
        if self.read(address, len(payload)) != payload:
            raise OSError("게임 모드 메모리 기록 검증에 실패했습니다")

    def protect(self, address, size, protection):
        old = W.DWORD()
        if not self.k.VirtualProtectEx(self.writer, C.c_void_p(address), size, protection, C.byref(old)):
            raise OSError("게임 모드 메모리 보호 변경에 실패했습니다")
        return old.value

    def flush(self, address, size):
        if not self.k.FlushInstructionCache(self.writer, C.c_void_p(address), size):
            raise OSError("게임 모드 명령 캐시 갱신에 실패했습니다")

    def allocate_near(self, site):
        origin = site & ~0xFFFF
        for step in range(1, 32760):
            for address in (origin + step * 0x10000, origin - step * 0x10000):
                if 0x10000 <= address <= 0x7FFFFFFFFFFF - ALLOCATION_SIZE:
                    result = self.k.VirtualAllocEx(self.writer, C.c_void_p(address), ALLOCATION_SIZE, 0x3000, 4)
                    if result:
                        rel_call(site, result)
                        return result
        raise OSError("안전한 근거리 게임 모드 공간을 확보하지 못했습니다")

    def clock(self):
        now, frequency = C.c_longlong(), C.c_longlong()
        if not self.k.QueryPerformanceCounter(C.byref(now)) or not self.k.QueryPerformanceFrequency(C.byref(frequency)) or frequency.value <= 0:
            raise OSError("사체 모드 임시 유효시간을 확인하지 못했습니다")
        return now.value, frequency.value

    def is_running(self):
        code = W.DWORD()
        return bool(self.k.GetExitCodeProcess(self.writer, C.byref(code))) and code.value == 259

    def _thread_ids(self):
        snapshot = self.k.CreateToolhelp32Snapshot(4, 0)
        if snapshot == C.c_void_p(-1).value:
            raise OSError("게임 스레드 목록을 확인하지 못했습니다")
        try:
            entry = ThreadEntry(); entry.size = C.sizeof(entry)
            ids = set(); ok = self.k.Thread32First(snapshot, C.byref(entry))
            while ok:
                if entry.pid == self.game.pid:
                    ids.add(entry.tid)
                ok = self.k.Thread32Next(snapshot, C.byref(entry))
            if C.get_last_error() != 18:  # ERROR_NO_MORE_FILES
                raise OSError("게임 스레드 목록을 끝까지 확인하지 못했습니다")
            if not ids or len(ids) > 8192:
                raise OSError("게임 스레드 목록이 안정적이지 않습니다")
            return ids
        finally:
            self.k.CloseHandle(snapshot)

    @contextmanager
    def frozen_threads(self, site, length):
        handles = []
        try:
            expected = self._thread_ids()
            for tid in sorted(expected):
                handle = self.k.OpenThread(0x4A, False, tid)
                if not handle:
                    raise OSError("게임 스레드를 안전하게 중단하지 못했습니다")
                suspended = False
                try:
                    if self.k.GetProcessIdOfThread(handle) != self.game.pid:
                        raise OSError("게임 스레드 소속이 바뀌었습니다")
                    if self.k.SuspendThread(handle) == 0xFFFFFFFF:
                        raise OSError("게임 스레드를 일시 중단하지 못했습니다")
                    suspended = True
                    handles.append(handle)
                    # AMD64 CONTEXT must be 16-byte aligned. CONTEXT_CONTROL
                    # flags are at +48 and RIP at +248 (Windows SDK layout).
                    storage = C.create_string_buffer(1232 + 15)
                    aligned = (C.addressof(storage) + 15) & ~15
                    C.c_uint32.from_address(aligned + 48).value = 0x100001
                    if not self.k.GetThreadContext(handle, C.c_void_p(aligned)):
                        raise OSError("게임 스레드 실행 위치를 확인하지 못했습니다")
                    rip = C.c_uint64.from_address(aligned + 248).value
                    if site <= rip < site + length:
                        raise OSError("게임 스레드가 변경 위치를 실행 중이어서 설치하지 않았습니다")
                finally:
                    if not suspended:
                        self.k.CloseHandle(handle)
            if self._thread_ids() != expected or self._thread_ids() != expected:
                raise OSError("설치 중 게임 스레드 목록이 바뀌었습니다")
            yield
        finally:
            resume_error = False
            for handle in reversed(handles):
                if self.k.ResumeThread(handle) == 0xFFFFFFFF:
                    resume_error = True
                self.k.CloseHandle(handle)
            if resume_error:
                raise OSError("일부 게임 스레드 재개에 실패했습니다")
