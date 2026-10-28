"""Read-only validation of the current game's loaded animal/outline structures."""
import ctypes as C
from ctypes import wintypes as W
import hashlib
from pathlib import Path
import struct

EXE_NAME = "theHunterCotW_F.exe"
EXPECTED_SHA256 = "33c8306e52c5541a5b87e4af576f4149f3da0c23b36775372ec6c41adbab73ca"
SINGLETON_RVA = 0x27C5DC8
K = C.WinDLL("kernel32", use_last_error=True)


class ProcessEntry(C.Structure):
    _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("pid", W.DWORD),
                ("heap", C.c_size_t), ("module", W.DWORD), ("threads", W.DWORD),
                ("parent", W.DWORD), ("priority", W.LONG), ("flags", W.DWORD),
                ("exe", W.WCHAR * 260)]


class ModuleEntry(C.Structure):
    _fields_ = [("dwSize", W.DWORD), ("module", W.DWORD), ("pid", W.DWORD),
                ("global_usage", W.DWORD), ("process_usage", W.DWORD),
                ("base", C.c_void_p), ("size", W.DWORD), ("handle", W.HMODULE),
                ("name", W.WCHAR * 256), ("path", W.WCHAR * 260)]


K.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
K.CreateToolhelp32Snapshot.restype = W.HANDLE
K.Process32FirstW.argtypes = K.Process32NextW.argtypes = [W.HANDLE, C.POINTER(ProcessEntry)]
K.Module32FirstW.argtypes = K.Module32NextW.argtypes = [W.HANDLE, C.POINTER(ModuleEntry)]
K.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
K.OpenProcess.restype = W.HANDLE
K.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
K.ReadProcessMemory.restype = W.BOOL
K.CloseHandle.argtypes = [W.HANDLE]
K.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
K.QueryFullProcessImageNameW.restype = W.BOOL


class GameMemory:
    def __init__(self):
        self.handle = None
        snap = K.CreateToolhelp32Snapshot(2, 0)
        if snap == C.c_void_p(-1).value:
            raise C.WinError(C.get_last_error())
        processes = []
        try:
            entry = ProcessEntry(); entry.dwSize = C.sizeof(entry)
            ok = K.Process32FirstW(snap, C.byref(entry))
            while ok:
                if entry.exe.lower() == EXE_NAME.lower():
                    processes.append(entry.pid)
                ok = K.Process32NextW(snap, C.byref(entry))
        finally:
            K.CloseHandle(snap)
        if len(processes) != 1:
            raise RuntimeError(f"게임을 실행하고 사냥터에 들어가세요. 감지된 게임: {len(processes)}개")
        self.pid = processes[0]
        snap = K.CreateToolhelp32Snapshot(0x18, self.pid)
        if snap == C.c_void_p(-1).value:
            raise C.WinError(C.get_last_error())
        try:
            module = ModuleEntry(); module.dwSize = C.sizeof(module)
            ok = K.Module32FirstW(snap, C.byref(module))
            while ok and module.name.lower() != EXE_NAME.lower():
                ok = K.Module32NextW(snap, C.byref(module))
            if not ok:
                raise RuntimeError("실행 중인 게임 모듈을 확인하지 못했습니다.")
            self.base, self.module_size = module.base, module.size
        finally:
            K.CloseHandle(snap)
        self.handle = K.OpenProcess(0x410, False, self.pid)
        if not self.handle:
            raise C.WinError(C.get_last_error())
        try:
            image_path = C.create_unicode_buffer(32768)
            path_size = W.DWORD(len(image_path))
            if not K.QueryFullProcessImageNameW(self.handle, 0, image_path, C.byref(path_size)):
                raise C.WinError(C.get_last_error())
            self.exe = Path(image_path.value)
            if self.exe.name.lower() != EXE_NAME.lower():
                raise RuntimeError("실행 중인 게임 파일 이름을 확인하지 못했습니다.")
            with self.exe.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != EXPECTED_SHA256:
                raise RuntimeError("지원하지 않는 게임 버전입니다. 업데이트 확인 후 모드를 다시 실행하세요.")
        except Exception:
            self.close()
            raise

    def close(self):
        if self.handle:
            K.CloseHandle(self.handle)
            self.handle = None

    def read(self, address, size):
        if not 0x10000 <= address <= 0x7FFFFFFFFFFF or not 0 < size <= 2**20:
            raise ValueError("Invalid game-memory range")
        buffer = C.create_string_buffer(size); count = C.c_size_t()
        if not K.ReadProcessMemory(self.handle, address, buffer, size, C.byref(count)) or count.value != size:
            raise C.WinError(C.get_last_error())
        return buffer.raw

    def qword(self, address):
        return struct.unpack("<Q", self.read(address, 8))[0]

    def animals(self):
        singleton = self.qword(self.base + SINGLETON_RVA)
        manager = self.qword(singleton + 0xB8)
        context = {"singleton": hex(singleton), "manager": hex(manager),
                   "game_state_48": struct.unpack("<I", self.read(singleton + 0x48, 4))[0],
                   "world_flag_7c": self.read(singleton + 0x7C, 1)[0]}
        begin, end = struct.unpack("<QQ", self.read(manager + 0x28, 16))
        if not begin and not end:
            return [], dict(context, count=0)
        if not begin or end < begin or (end-begin) % 8 or (end-begin) // 8 > 4096:
            raise RuntimeError("사냥감 목록 구조가 검증된 버전과 달라 읽기를 중단했습니다.")
        count = (end-begin) // 8
        pointers = struct.unpack(f"<{count}Q", self.read(begin, count*8)) if count else []
        result, failed = [], 0
        for pointer in pointers:
            try:
                raw = self.read(pointer, 0x180)
                character, handle = struct.unpack_from("<QQ", raw)
                definition = struct.unpack_from("<Q", raw, 0x28)[0]
                vtable = self.qword(character) if character else 0
                valid_vtable = self.base <= vtable < self.base + self.module_size
                if not character or not definition or not valid_vtable:
                    failed += 1
                    continue
                outline = struct.unpack("<7f", self.read(character + 0x2468, 28))
                definition_path = None
                try:
                    path_pointer = self.qword(definition + 0xC0)
                    path_bytes = self.read(path_pointer, 240).split(b"\0", 1)[0]
                    if b"/animals/" in path_bytes or b"/birds/" in path_bytes:
                        definition_path = path_bytes.decode("ascii")
                except (OSError, ValueError, UnicodeError):
                    pass
                result.append({"wrapper": hex(pointer), "character": hex(character),
                               "definition": hex(definition), "vtable_rva": hex(vtable-self.base),
                               "definition_path_c0": definition_path,
                               "position_140": struct.unpack_from("<3f", raw, 0x140),
                               "position_148": struct.unpack_from("<3f", raw, 0x148),
                               "state_cc": struct.unpack_from("<I", raw, 0xCC)[0],
                               "flags_d4": struct.unpack_from("<I", raw, 0xD4)[0],
                               "hp_178": struct.unpack_from("<2f", raw, 0x178),
                               "outline_2468": outline})
            except (OSError, ValueError, struct.error):
                failed += 1
        return result, dict(context, count=count, validated=len(result), failed=failed)
