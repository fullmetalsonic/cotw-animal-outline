"""Temporary single-player memory modes; no direct game or save file edits."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import math
from pathlib import Path
import queue
import struct
import threading
import time

import game_memory as probe
from app_version import VERSION
from ninja_mode import TransientNinjaState
from pet_outline import TransientPetState
from hellhound_mode import TransientHellhoundState
from update_check import UpdateResult, check_update, is_release_url

OUTLINE_OFFSET = 0x2468
OUTLINES = {
    "blue": (0.0, 0.55, 1.0, 1.0, 0.30, 0.10, 0.10),
    "white": (1.0, 1.0, 1.0, 1.0, 0.30, 0.10, 0.10),
}
PAYLOADS = {color: struct.pack("<7f", *outline) for color, outline in OUTLINES.items()}
COLOR_LABELS = {"blue": "파랑", "white": "흰색"}
# Default exports retained for the existing white-mode diagnostic.
OUTLINE, PAYLOAD = OUTLINES["white"], PAYLOADS["white"]
INTERVAL = 0.05
# Current build's 16/16 live wild-animal samples; resource path is also required.
VERIFIED_WILD_VTABLE_RVAS = frozenset({0x1A60028})
CODE_SIGNATURES = {
    0x6A0D70: bytes.fromhex("0f1002f30f11917c2400000f118168240000f30f10442428f30f118178240000f30f119980240000c3"),
    0x6B1810: bytes.fromhex("40534883ec40f30f10a1742400000f57c00f2fe0488bd90f297424300f28d1f3"),
}

K = probe.K
K.WriteProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
K.WriteProcessMemory.restype = W.BOOL
K.GetExitCodeProcess.argtypes = [W.HANDLE, C.POINTER(W.DWORD)]
K.GetExitCodeProcess.restype = W.BOOL
K.CreateMutexW.argtypes = [C.c_void_p, W.BOOL, W.LPCWSTR]
K.CreateMutexW.restype = W.HANDLE
MUTEX_NAME = r"Local\COTW_WildAnimalOutlineMod"


def acquire_single_instance(api=K, get_error=C.get_last_error):
    C.set_last_error(0)
    handle = api.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        raise RuntimeError("중복 실행 상태를 확인하지 못해 모드를 시작하지 않았습니다")
    if get_error() == 183:  # ERROR_ALREADY_EXISTS
        api.CloseHandle(handle)
        return None
    return handle


def typed_write(api, handle, address, payload):
    if not isinstance(payload, bytes) or len(payload) != 28:
        raise ValueError("윤곽 쓰기는 정확히 28바이트여야 합니다")
    if not 0x10000 <= address <= 0x7FFFFFFFFFFF - len(payload):
        raise ValueError("잘못된 윤곽 주소입니다")
    values = struct.unpack("<7f", payload)
    if not all(math.isfinite(v) for v in values) or not 0 < values[4] <= 1:
        raise ValueError("유한한 임시 윤곽 값만 허용합니다")
    buffer = C.create_string_buffer(payload, len(payload))
    count = C.c_size_t()
    if not api.WriteProcessMemory(handle, C.c_void_p(address), buffer, len(payload), C.byref(count)) or count.value != len(payload):
        raise RuntimeError("윤곽 메모리 쓰기에 실패하여 모드를 중지했습니다")


def identity(row):
    return tuple(int(row[key], 16) if isinstance(row[key], str) else row[key]
                 for key in ("wrapper", "character", "definition", "vtable_rva", "state_cc", "flags_d4"))


def wild_resource_path(path):
    if not isinstance(path, str):
        return False
    path = path.replace("\\", "/").lower()
    if not path.startswith(("animations/hp_ragdoll/animals/", "animations/hp_ragdoll/birds/")) or not path.endswith(".ragdoll"):
        return False
    if ".." in path.split("/") or any(part in {"dog", "dogs", "retriever", "pointer"} for part in path.split("/")):
        return False
    compact = "".join(char for char in path if char.isalnum())
    return not any(breed in compact for breed in ("bloodhound", "labrador", "germanshorthairedpointer", "germanpointer"))


def health_matches(values, corpse=False):
    if not isinstance(values, (tuple, list)) or len(values) != 2:
        return False
    maximum, current = values
    return (all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)
            and maximum > 0 and ((current <= 0) if corpse else (current > 0)))


class StaleTarget(RuntimeError):
    """A single animal no longer matches its snapshot; never authorizes a write."""


class LiveBackend:
    def __init__(self, color="white"):
        self.writer = None
        self.set_color(color)
        self.game = probe.GameMemory()
        self.file_stamp = self._stamp()
        self.corpse_renderer = None
        self.corpse_writer = None
        self.ninja_mode = None
        self.ninja_writer = None
        self.pet_keeper = None
        self.pet_writer = None
        self.hellhound_mode = None
        self.hellhound_writer = None

    def set_color(self, color):
        if color not in PAYLOADS:
            raise ValueError("지원하는 윤곽 색상은 blue 또는 white입니다")
        if self.writer is not None:
            raise RuntimeError("색상은 쓰기를 중지한 OFF 상태에서 변경하세요")
        self.color, self.payload = color, PAYLOADS[color]

    def _stamp(self):
        stat = self.game.exe.stat()
        return stat.st_size, stat.st_mtime_ns

    def check(self):
        code = W.DWORD()
        if not K.GetExitCodeProcess(self.game.handle, C.byref(code)) or code.value != 259:
            raise RuntimeError("게임이 종료되어 모드를 껐습니다")
        if self._stamp() != self.file_stamp:
            raise RuntimeError("게임 파일이 변경되어 모드를 껐습니다")
        for rva, expected in CODE_SIGNATURES.items():
            if self.game.read(self.game.base + rva, len(expected)) != expected:
                raise RuntimeError("게임 실행 코드가 검증 버전과 달라 모드를 껐습니다")

    def snapshot(self):
        self.check()
        rows, summary = self.game.animals()
        singleton = int(summary["singleton"], 16)
        if not singleton or struct.unpack("<I", self.game.read(singleton + 0x48, 4))[0] != 7 or self.game.read(singleton + 0x7C, 1) == b"\0":
            raise RuntimeError("사냥터를 불러오는 중이거나 사냥터를 벗어나 모드를 껐습니다")
        context = (singleton, int(summary["manager"], 16))
        return rows, context, summary

    def start_writing(self):
        if not VERIFIED_WILD_VTABLE_RVAS:
            raise RuntimeError("이 빌드의 사냥감 구분 검증이 아직 완료되지 않았습니다")
        self.check()
        if self.writer is None:
            self.writer = K.OpenProcess(0x438, False, self.game.pid)
            if not self.writer:
                raise RuntimeError("게임 프로세스 접근 권한을 얻지 못했습니다. 게임과 모드의 실행 권한을 확인하세요.")

    def stop_writing(self):
        if self.writer:
            K.CloseHandle(self.writer)
            self.writer = None

    def wild_candidate(self, row):
        return (int(row["vtable_rva"], 16) in VERIFIED_WILD_VTABLE_RVAS
                and wild_resource_path(row.get("definition_path_c0"))
                and bool(row["flags_d4"] & 4) and row["state_cc"] != 0xDEADBEEF)

    def eligible(self, row):
        return self.wild_candidate(row) and health_matches(row.get("hp_178"))

    def eligible_corpse(self, row):
        return self.wild_candidate(row) and health_matches(row.get("hp_178"), corpse=True)

    def validate(self, row, context, corpse=False):
        singleton, manager = context
        if self.game.qword(self.game.base + probe.SINGLETON_RVA) != singleton or self.game.qword(singleton + 0xB8) != manager:
            raise RuntimeError("사냥터 연결이 바뀌어 모드를 껐습니다")
        wrapper, character, definition, vtable_rva, state_cc, flags = identity(row)
        try:
            raw = self.game.read(wrapper, 0xD8)
            now_character = struct.unpack_from("<Q", raw)[0]
            now_definition = struct.unpack_from("<Q", raw, 0x28)[0]
            now_state = struct.unpack_from("<I", raw, 0xCC)[0]
            now_flags = struct.unpack_from("<I", raw, 0xD4)[0]
            if (now_character, now_definition) != (character, definition):
                raise StaleTarget("사냥감 포인터가 바뀌어 이번 갱신에서 제외했습니다")
            # Ordinary animal state/flag changes do not change object identity.
            # Use the same renderable bit as the game's own outline wrapper.
            if now_state == 0xDEADBEEF or not now_flags & 4:
                raise StaleTarget("사냥감이 해제되거나 렌더링 대상에서 빠졌습니다")
            if self.game.qword(character) != self.game.base + vtable_rva:
                raise StaleTarget("사냥감 캐릭터가 바뀌었습니다")
            path_pointer = self.game.qword(definition + 0xC0)
            path = self.game.read(path_pointer, 240).split(b"\0", 1)[0].decode("ascii")
            if path != row.get("definition_path_c0") or not wild_resource_path(path):
                raise StaleTarget("사냥감 리소스 경로가 바뀌었습니다")
            if not self.wild_candidate(row):
                raise StaleTarget("검증되지 않은 사냥감은 갱신하지 않습니다")
            health = struct.unpack("<2f", self.game.read(wrapper + 0x178, 8))
            if not health_matches(health, corpse):
                raise StaleTarget("사냥감의 생존 상태가 바뀌어 다음 목록에서 확인합니다")
            # The game owns these objects; a final identity check narrows, but
            # cannot eliminate, concurrent object-release races in a helper.
            if self.game.qword(wrapper) != character:
                raise StaleTarget("사냥감이 해제되었습니다")
        except (OSError, ValueError, struct.error) as error:
            raise StaleTarget("사냥감 메모리를 더 이상 읽을 수 없습니다") from error

    def write(self, row):
        if not self.writer:
            raise RuntimeError("쓰기 핸들이 닫혀 있습니다")
        typed_write(K, self.writer, int(row["character"], 16) + OUTLINE_OFFSET, self.payload)

    def refresh_corpses(self, rows, context, color):
        candidates = []
        for row in rows:
            if not self.eligible_corpse(row):
                continue
            try:
                self.validate(row, context, corpse=True)
            except StaleTarget:
                continue
            candidates.append(row)
        if candidates and self.corpse_renderer is None:
            from corpse_outline import CorpseRenderer
            self.check()
            self.corpse_writer = K.OpenProcess(0x438, False, self.game.pid)
            if not self.corpse_writer:
                raise RuntimeError("사체 표시를 위한 게임 프로세스 접근 권한을 얻지 못했습니다")
            try:
                self.corpse_renderer = CorpseRenderer(self.game, self.corpse_writer)
            except Exception:
                K.CloseHandle(self.corpse_writer)
                self.corpse_writer = None
                raise
        if self.corpse_renderer:
            return self.corpse_renderer.publish(candidates, color)
        return 0

    def stop_corpses(self):
        if self.corpse_renderer:
            self.corpse_renderer.disable()

    def refresh_ninja(self):
        if self.ninja_mode is None:
            from ninja_mode import NinjaMode
            self.check()
            self.ninja_writer = K.OpenProcess(0x438, False, self.game.pid)
            if not self.ninja_writer:
                raise RuntimeError("닌자 모드를 위한 게임 프로세스 접근 권한을 얻지 못했습니다")
            try:
                self.ninja_mode = NinjaMode(self.game, self.ninja_writer)
            except Exception:
                K.CloseHandle(self.ninja_writer)
                self.ninja_writer = None
                raise
        self.ninja_mode.publish()

    def stop_ninja(self):
        if self.ninja_mode:
            self.ninja_mode.disable()

    def refresh_pet(self):
        if self.pet_keeper is None:
            from pet_outline import PetOutlineKeeper
            self.check()
            self.pet_writer = K.OpenProcess(0x438, False, self.game.pid)
            if not self.pet_writer:
                raise RuntimeError("반려견 윤곽을 위한 게임 프로세스 접근 권한을 얻지 못했습니다")
            try:
                self.pet_keeper = PetOutlineKeeper(self.game, self.pet_writer)
            except Exception:
                K.CloseHandle(self.pet_writer)
                self.pet_writer = None
                raise
        self.pet_keeper.publish()

    def stop_pet(self):
        if self.pet_keeper:
            self.pet_keeper.disable()

    def refresh_hellhound(self):
        if self.hellhound_mode is None:
            from hellhound_mode import HellhoundMode
            self.check()
            self.hellhound_writer = K.OpenProcess(0x438, False, self.game.pid)
            if not self.hellhound_writer:
                raise RuntimeError("헬하운드를 위한 게임 프로세스 접근 권한을 얻지 못했습니다")
            try:
                self.hellhound_mode = HellhoundMode(self.game, self.hellhound_writer)
            except Exception:
                K.CloseHandle(self.hellhound_writer)
                self.hellhound_writer = None
                raise
        self.hellhound_mode.publish()

    def stop_hellhound(self):
        if self.hellhound_mode:
            self.hellhound_mode.disable()

    def close(self):
        try:
            if self.corpse_renderer:
                self.corpse_renderer.close()
        finally:
            try:
                if self.ninja_mode:
                    self.ninja_mode.close()
            finally:
                try:
                    if self.pet_keeper:
                        self.pet_keeper.close()
                finally:
                    try:
                        if self.hellhound_mode:
                            self.hellhound_mode.close()
                    finally:
                        for name in ("corpse_writer", "ninja_writer", "pet_writer", "hellhound_writer"):
                            handle = getattr(self, name)
                            if handle:
                                K.CloseHandle(handle)
                                setattr(self, name, None)
                        self.stop_writing()
                        self.game.close()


class RefreshController:
    def __init__(self):
        self.lock = threading.Lock()
        self.enabled = False
        self.context = None

    def enable(self, context):
        with self.lock:
            self.context = context
            self.enabled = True

    def enable_if_requested(self, context, requested, stopping):
        with self.lock:
            if requested.is_set() and not stopping.is_set():
                self.context = context
                self.enabled = True

    def disable(self):
        # Once this returns, a worker cannot begin another write.
        with self.lock:
            self.enabled = False
            self.context = None

    def tick(self, backend, snapshot=None):
        try:
            backend.check()
            rows, context, summary = snapshot if snapshot is not None else backend.snapshot()
            count = 0
            for row in rows:
                with self.lock:
                    if not self.enabled:
                        break
                    if context != self.context:
                        raise RuntimeError("사냥터 연결이 바뀌어 모드를 껐습니다")
                    if not backend.eligible(row):
                        continue
                    try:
                        backend.validate(row, context)
                    except StaleTarget:
                        continue
                    backend.write(row)
                    count += 1
            if context != self.context and self.enabled:
                raise RuntimeError("사냥터 연결이 바뀌어 모드를 껐습니다")
            return count, summary
        except Exception:
            self.disable()
            raise


class ModWorker(threading.Thread):
    def __init__(self, color="white"):
        if color not in PAYLOADS:
            raise ValueError("지원하는 윤곽 색상은 blue 또는 white입니다")
        super().__init__(daemon=True)
        self.color = color
        self.color_lock = threading.Lock()
        self.requested = threading.Event()
        self.corpse_requested = threading.Event()
        self.corpse_color = (1.0, 0.35, 0.0)
        self.ninja_requested = threading.Event()
        self.pet_requested = threading.Event()
        self.hellhound_requested = threading.Event()
        self.stopping = threading.Event()
        self.messages = queue.Queue()
        self.controller = RefreshController()

    def off(self):
        self.requested.clear()
        self.controller.disable()

    def close(self):
        self.off()
        self.corpse_off()
        self.ninja_off()
        self.pet_off()
        self.hellhound_off()
        self.stopping.set()

    def ninja_off(self):
        self.ninja_requested.clear()

    def pet_off(self):
        self.pet_requested.clear()

    def hellhound_off(self):
        self.hellhound_requested.clear()

    def corpse_off(self):
        self.corpse_requested.clear()

    def set_corpse_color(self, color):
        if (not isinstance(color, (tuple, list)) or len(color) != 3
                or not all(isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1 for v in color)):
            raise ValueError("사체 색상은 0~1 범위의 RGB 값이어야 합니다")
        self.corpse_off()
        with self.color_lock:
            self.corpse_color = tuple(color)

    def set_color(self, color):
        if color not in PAYLOADS:
            raise ValueError("지원하는 윤곽 색상은 blue 또는 white입니다")
        self.off()
        # Only the worker touches its backend; the GUI passes a plain selection.
        with self.color_lock:
            self.color = color

    def run(self):
        backend = None
        last_poll = 0
        last_error = None
        try:
            while not self.stopping.is_set():
                try:
                    if backend is None:
                        with self.color_lock:
                            backend = LiveBackend(self.color)
                    if not self.requested.is_set():
                        backend.stop_writing()
                    if not self.corpse_requested.is_set():
                        backend.stop_corpses()
                    if not self.ninja_requested.is_set():
                        backend.stop_ninja()
                    if not self.pet_requested.is_set():
                        backend.stop_pet()
                    if not self.hellhound_requested.is_set():
                        backend.stop_hellhound()
                    active = (self.requested.is_set() or self.corpse_requested.is_set()
                              or self.ninja_requested.is_set() or self.pet_requested.is_set()
                              or self.hellhound_requested.is_set())
                    if active or time.monotonic() - last_poll >= 1:
                        rows, context, summary = backend.snapshot()
                        count = sum(backend.eligible(row) for row in rows)
                        corpse_count = sum(backend.eligible_corpse(row) for row in rows)
                        if self.requested.is_set() and not self.controller.enabled:
                            with self.color_lock:
                                backend.stop_writing()
                                backend.set_color(self.color)
                                backend.start_writing()
                                self.controller.enable_if_requested(context, self.requested, self.stopping)
                        if self.controller.enabled:
                            count, summary = self.controller.tick(backend, (rows, context, summary))
                        if self.corpse_requested.is_set():
                            with self.color_lock:
                                corpse_color = self.corpse_color
                            corpse_count = backend.refresh_corpses(rows, context, corpse_color)
                            if not self.corpse_requested.is_set():
                                backend.stop_corpses()
                        ninja_state = "닌자 OFF"
                        if self.ninja_requested.is_set():
                            ninja_state = "닌자 ON"
                            try:
                                backend.refresh_ninja()
                            except TransientNinjaState:
                                # publish has disabled its leases; keep the user's
                                # selection while the next tick rechecks identity.
                                ninja_state = "닌자 ON · 상태 전환 대기"
                            if not self.ninja_requested.is_set():
                                backend.stop_ninja()
                                ninja_state = "닌자 OFF"
                        pet_state = "반려견 윤곽 OFF"
                        if self.pet_requested.is_set():
                            pet_state = "반려견 윤곽 ON"
                            try:
                                backend.refresh_pet()
                            except TransientPetState:
                                pet_state = "반려견 윤곽 ON · 연결 대기"
                            if not self.pet_requested.is_set():
                                backend.stop_pet()
                                pet_state = "반려견 윤곽 OFF"
                        hellhound_state = "헬하운드 OFF"
                        if self.hellhound_requested.is_set():
                            hellhound_state = "헬하운드 ON"
                            try:
                                backend.refresh_hellhound()
                            except TransientHellhoundState:
                                hellhound_state = "헬하운드 ON · 연결 대기"
                            if not self.hellhound_requested.is_set():
                                backend.stop_hellhound()
                                hellhound_state = "헬하운드 OFF"
                        if active:
                            last_error = None
                        live_on = self.requested.is_set() and self.controller.enabled
                        detail = (f"살아 있는 사냥감의 {COLOR_LABELS[backend.color]} 윤곽을 갱신하고 있습니다." if live_on
                                  else last_error or "살아 있는 사냥감의 윤곽 갱신이 중지되었습니다.")
                        self.messages.put(("모드 ON" if live_on else "연결됨 · 모드 OFF", count, detail,
                                           "사체 ON" if self.corpse_requested.is_set() else "사체 OFF", corpse_count,
                                           ninja_state, pet_state, hellhound_state))
                        last_poll = time.monotonic()
                except Exception as error:
                    was_on = (self.requested.is_set() or self.controller.enabled or self.corpse_requested.is_set()
                              or self.ninja_requested.is_set() or self.pet_requested.is_set()
                              or self.hellhound_requested.is_set())
                    if was_on:
                        last_error = str(error)
                    self.off()
                    self.corpse_off()
                    self.ninja_off()
                    self.pet_off()
                    self.hellhound_off()
                    if backend:
                        try:
                            backend.close()
                        except OSError:
                            # Stopped heartbeat leases expire even if disconnect
                            # loses process access while the game is shutting down.
                            pass
                        finally:
                            backend = None
                    self.messages.put(("오류 · 모드 OFF" if was_on else "게임 연결 대기 · 모드 OFF", 0, str(error), "사체 OFF", 0, "닌자 OFF", "반려견 윤곽 OFF", "헬하운드 OFF"))
                    self.stopping.wait(1)
                self.stopping.wait(INTERVAL)
        finally:
            self.controller.disable()
            if backend:
                try:
                    backend.close()
                except OSError:
                    pass  # Native leases expire without this worker.


def gui(color="white"):
    if color not in PAYLOADS:
        raise ValueError("지원하는 윤곽 색상은 blue 또는 white입니다")
    from tkinter import messagebox
    try:
        mutex = acquire_single_instance()
    except RuntimeError as error:
        messagebox.showerror("COTW 사냥감 윤곽 모드", str(error))
        return
    if mutex is None:
        messagebox.showinfo("COTW 사냥감 윤곽 모드", "사냥감 윤곽 모드가 이미 열려 있습니다.\n기존 창에서 ON/OFF를 조작하세요.")
        return
    try:
        run_gui(color)
    finally:
        K.CloseHandle(mutex)


def run_gui(color="white"):
    import tkinter as tk
    from tkinter import colorchooser, ttk
    shell = C.WinDLL("shell32")
    shell.SetCurrentProcessExplicitAppUserModelID.argtypes = [W.LPCWSTR]
    shell.SetCurrentProcessExplicitAppUserModelID.restype = C.c_long
    shell.SetCurrentProcessExplicitAppUserModelID("Local.COTW.WildAnimalOutlineMod")
    root = tk.Tk()
    root.title("COTW 사냥감 윤곽 모드")
    root.geometry(f"590x{max(550, min(1040, root.winfo_screenheight() - 90))}")
    root.minsize(490, 550)
    shell_panel = ttk.Frame(root)
    shell_panel.pack(fill="both", expand=True)
    canvas = tk.Canvas(shell_panel, highlightthickness=0)
    scrollbar = ttk.Scrollbar(shell_panel, orient="vertical", command=canvas.yview)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    canvas.configure(yscrollcommand=scrollbar.set)
    panel = ttk.Frame(canvas, padding=22)
    panel_window = canvas.create_window((0, 0), window=panel, anchor="nw")
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(panel_window, width=event.width))
    canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(-int(event.delta / 120), "units"))
    ttk.Label(panel, text="사냥감 · 사체 · 반려견 · 닌자 모드", font=("맑은 고딕", 17, "bold")).pack(anchor="w")
    ttk.Label(panel, text="대상 빌드: 26051119 · 싱글플레이 전용").pack(anchor="w", pady=(5, 18))
    status = tk.StringVar(value="게임 연결 확인 중 · 모드 OFF")
    count = tk.StringVar(value="살아 있는 사냥감: 0마리")
    detail = tk.StringVar(value="사냥터를 불러온 뒤 모드를 켜세요.")
    ttk.Label(panel, textvariable=status, font=("맑은 고딕", 12, "bold")).pack(anchor="w")
    ttk.Label(panel, textvariable=count).pack(anchor="w", pady=8)
    worker = ModWorker(color)
    color_selection = tk.StringVar(value=color)
    color_panel = ttk.Frame(panel)
    color_panel.pack(anchor="w", fill="x", pady=5)
    ttk.Label(color_panel, text="윤곽 색상 (OFF에서 선택):").pack(side="left", padx=(0, 10))
    color_buttons = []

    def choose_color():
        worker.set_color(color_selection.get())
        status.set("모드 OFF")
        detail.set(f"{COLOR_LABELS[color_selection.get()]}을 선택했습니다. 모드 ON을 누르면 적용됩니다.")

    for value in ("white", "blue"):
        button = ttk.Radiobutton(color_panel, text=COLOR_LABELS[value], value=value,
                                 variable=color_selection, command=choose_color)
        button.pack(side="left", padx=5)
        color_buttons.append(button)
    buttons = ttk.Frame(panel)
    buttons.pack(fill="x", pady=8)

    def on():
        for button in color_buttons:
            button.state(["disabled"])
        worker.requested.set()

    ttk.Button(buttons, text="모드 ON", command=on).pack(side="left", fill="x", expand=True, padx=(0, 6))

    def off():
        worker.off()
        for button in color_buttons:
            button.state(["!disabled"])
        status.set("모드 OFF")
        detail.set("윤곽 갱신을 중지했습니다. 임시 윤곽은 게임 진행 중 잠시 후 사라집니다.")

    ttk.Button(buttons, text="모드 OFF", command=off).pack(side="left", fill="x", expand=True)
    detail_label = ttk.Label(panel, textvariable=detail, wraplength=465)
    detail_label.pack(anchor="w", fill="x", pady=12)
    corpse_panel = ttk.LabelFrame(panel, text="사체 표시 · 독립 ON/OFF", padding=10)
    corpse_panel.pack(fill="x", pady=(0, 10))
    corpse_status = tk.StringVar(value="사체 OFF · 대상 0마리")
    corpse_hex = tk.StringVar(value="사체 색상: #FF5900 · 변경")
    ttk.Label(corpse_panel, textvariable=corpse_status).pack(anchor="w", pady=(0, 7))

    def choose_corpse_color():
        selected, hex_color = colorchooser.askcolor(color="#%02x%02x%02x" % tuple(
            round(v * 255) for v in worker.corpse_color), parent=root, title="사체 윤곽 색상")
        if selected is not None:
            worker.set_corpse_color(tuple(v / 255.0 for v in selected))
            corpse_hex.set(f"사체 색상: {hex_color.upper()} · 변경")

    corpse_color_button = ttk.Button(corpse_panel, textvariable=corpse_hex, command=choose_corpse_color)
    corpse_color_button.pack(anchor="w", fill="x")
    corpse_buttons = ttk.Frame(corpse_panel)
    corpse_buttons.pack(fill="x", pady=8)

    def corpse_on():
        corpse_color_button.state(["disabled"])
        worker.corpse_requested.set()

    def corpse_off():
        worker.corpse_off()
        corpse_color_button.state(["!disabled"])
        corpse_status.set("사체 OFF")

    ttk.Button(corpse_buttons, text="사체 ON", command=corpse_on).pack(side="left", fill="x", expand=True, padx=(0, 6))
    ttk.Button(corpse_buttons, text="사체 OFF", command=corpse_off).pack(side="left", fill="x", expand=True)
    corpse_help = ttk.Label(corpse_panel, text="사체만 별도 색상으로 표시합니다. OFF에서는 게임의 기본 사체 표시로 돌아갑니다.",
                            wraplength=440)
    corpse_help.pack(anchor="w", fill="x")
    ninja_panel = ttk.LabelFrame(panel, text="닌자 모드 · 독립 ON/OFF", padding=10)
    ninja_panel.pack(fill="x", pady=(0, 10))
    ninja_status = tk.StringVar(value="닌자 OFF")
    ttk.Label(ninja_panel, textvariable=ninja_status).pack(anchor="w", pady=(0, 7))
    ninja_buttons = ttk.Frame(ninja_panel)
    ninja_buttons.pack(fill="x", pady=(0, 8))

    def ninja_on():
        worker.ninja_requested.set()

    def ninja_off():
        worker.ninja_off()
        ninja_status.set("닌자 OFF")

    ttk.Button(ninja_buttons, text="닌자 ON", command=ninja_on).pack(side="left", fill="x", expand=True, padx=(0, 6))
    ttk.Button(ninja_buttons, text="닌자 OFF", command=ninja_off).pack(side="left", fill="x", expand=True)
    ninja_help = ttk.Label(ninja_panel, text="이동·탈것 소음과 플레이어의 모습에 대한 AI 감지를 차단합니다. 효과음과 게임 소음 게이지는 유지되며, 냄새·발포 감지는 그대로입니다. 승하차 같은 상태 전환에는 잠시 대기 후 자동으로 다시 적용합니다.",
                          wraplength=440)
    ninja_help.pack(anchor="w", fill="x")

    pet_panel = ttk.LabelFrame(panel, text="반려견 윤곽 유지 · 독립 ON/OFF", padding=10)
    pet_panel.pack(fill="x", pady=(0, 10))
    pet_status = tk.StringVar(value="반려견 윤곽 OFF")
    ttk.Label(pet_panel, textvariable=pet_status).pack(anchor="w", pady=(0, 7))
    pet_buttons = ttk.Frame(pet_panel)
    pet_buttons.pack(fill="x", pady=(0, 8))

    def pet_on():
        worker.pet_requested.set()

    def pet_off():
        worker.pet_off()
        pet_status.set("반려견 윤곽 OFF")

    ttk.Button(pet_buttons, text="반려견 윤곽 ON", command=pet_on).pack(side="left", fill="x", expand=True, padx=(0, 6))
    ttk.Button(pet_buttons, text="반려견 윤곽 OFF", command=pet_off).pack(side="left", fill="x", expand=True)
    pet_help = ttk.Label(pet_panel, text="전체 동물 흔적 숨김을 유지하면서 반려견 윤곽만 표시합니다. 게임의 사냥개 윤곽 켜기·색상과 원래 가림 판정을 따릅니다. 닌자 효과는 반려견에도 유지됩니다.", wraplength=440)
    pet_help.pack(anchor="w", fill="x")

    hellhound_panel = ttk.LabelFrame(panel, text="헬하운드 모드 · 독립 ON/OFF", padding=10)
    hellhound_panel.pack(fill="x", pady=(0, 10))
    hellhound_status = tk.StringVar(value="헬하운드 OFF")
    ttk.Label(hellhound_panel, textvariable=hellhound_status).pack(anchor="w", pady=(0, 7))
    hellhound_buttons = ttk.Frame(hellhound_panel)
    hellhound_buttons.pack(fill="x", pady=(0, 8))

    def hellhound_off():
        worker.hellhound_off()
        hellhound_status.set("헬하운드 OFF")

    ttk.Button(hellhound_buttons, text="헬하운드 ON", command=worker.hellhound_requested.set).pack(side="left", fill="x", expand=True, padx=(0, 6))
    ttk.Button(hellhound_buttons, text="헬하운드 OFF", command=hellhound_off).pack(side="left", fill="x", expand=True)
    hellhound_help = ttk.Label(hellhound_panel, text="리트리버가 1~9등급 사체를 회수하도록 허용합니다. 원래 거리·상태 조건은 유지합니다. 큰 사체는 픽업 성공 시 플레이어 약 3m 앞에 옮깁니다. 사체를 E로 정상 수확할 수 있으며 실제 등급·무게는 바꾸지 않습니다. 리트리버 DLC와 활성 반려견이 필요합니다.", wraplength=440)
    hellhound_help.pack(anchor="w", fill="x")
    updates_panel = ttk.LabelFrame(panel, text="업데이트", padding=9)
    updates_panel.pack(fill="x", pady=(3, 0))
    versions = tk.StringVar(value=f"현재 {VERSION} / 최신 확인 중")
    update_message = tk.StringVar(value="확인 중에도 모드를 사용할 수 있습니다.")
    ttk.Label(updates_panel, textvariable=versions).pack(anchor="w")
    update_label = ttk.Label(updates_panel, textvariable=update_message, wraplength=450)
    update_label.pack(anchor="w", fill="x", pady=5)
    update_buttons = ttk.Frame(updates_panel)
    update_buttons.pack(fill="x")
    update_results = queue.Queue()
    update_running = False
    release_link = None

    def request_update():
        nonlocal update_running
        if update_running:
            return
        update_running = True
        check_button.state(["disabled"])
        update_message.set("최신 정식 배포를 확인하고 있습니다.")

        def fetch():
            try:
                result = check_update()
            except Exception:
                result = UpdateResult("unavailable")
            update_results.put(result)

        threading.Thread(target=fetch, daemon=True).start()

    def open_release():
        if release_link and is_release_url(release_link):
            import webbrowser
            webbrowser.open(release_link)

    check_button = ttk.Button(update_buttons, text="업데이트 확인", command=request_update)
    check_button.pack(side="left")
    release_button = ttk.Button(update_buttons, text="배포 페이지 열기", command=open_release, state="disabled")
    release_button.pack(side="left", padx=8)

    def resize(event):
        detail_label.configure(wraplength=max(260, event.width - 45))
        update_label.configure(wraplength=max(240, event.width - 65))
        corpse_help.configure(wraplength=max(240, event.width - 65))
        ninja_help.configure(wraplength=max(240, event.width - 65))
        pet_help.configure(wraplength=max(240, event.width - 65))
        hellhound_help.configure(wraplength=max(240, event.width - 65))
        canvas.configure(scrollregion=canvas.bbox("all"))

    panel.bind("<Configure>", resize)
    worker.start()

    def poll():
        nonlocal update_running, release_link
        for button in color_buttons:
            button.state(["disabled"] if worker.requested.is_set() or worker.controller.enabled else ["!disabled"])
        corpse_color_button.state(["disabled"] if worker.corpse_requested.is_set() else ["!disabled"])
        latest = None
        while True:
            try:
                latest = worker.messages.get_nowait()
            except queue.Empty:
                break
        if latest and not (latest[0] == "모드 ON" and not worker.requested.is_set()):
            status.set(latest[0])
            count.set(f"살아 있는 사냥감: {latest[1]}마리")
            detail.set(latest[2])
            corpse_status.set(f"{latest[3]} · 대상 {latest[4]}마리")
            ninja_status.set(latest[5])
            pet_status.set(latest[6])
            hellhound_status.set(latest[7])
        try:
            result = update_results.get_nowait()
        except queue.Empty:
            pass
        else:
            update_running = False
            check_button.state(["!disabled"])
            versions.set(f"현재 {VERSION} / 최신 {result.latest or '확인 불가'}")
            update_message.set(result.message)
            release_link = result.release_url if is_release_url(result.release_url) else None
            release_button.state(["!disabled"] if release_link else ["disabled"])
        root.after(100, poll)

    def closing():
        worker.close()
        status.set("모드 OFF · 종료 중")
        if worker.is_alive():
            root.after(50, closing)
        else:
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", closing)
    root.after(100, poll)
    root.after(250, request_update)
    root.mainloop()


def self_test():
    for path in ("animations/hp_ragdoll/birds/pheasant/pheasant_internal_ragdoll_100.ragdoll",
                 "animations/hp_ragdoll/animals/mexican_bobcat/a.ragdoll",
                 "animations/hp_ragdoll/animals/raccoon_dog/a.ragdoll"):
        assert wild_resource_path(path)
    for path in (None, "characters/player.ragdoll", "animations/hp_ragdoll/animals/dog/a.ragdoll",
                 "animations/hp_ragdoll/animals/bloodhound/a.ragdoll", "animations/hp_ragdoll/animals/labrador_retriever/a.ragdoll",
                 "animations/hp_ragdoll/animals/german_shorthaired_pointer/a.ragdoll",
                 "animations/hp_ragdoll/animals/../dogs/a.ragdoll"):
        assert not wild_resource_path(path)

    class FakeAPI:
        def __init__(self, fail=False):
            self.fail, self.calls = fail, []

        def WriteProcessMemory(self, handle, address, data, size, count):
            self.calls.append((handle, address.value, C.string_at(data, size), size))
            C.cast(count, C.POINTER(C.c_size_t))[0] = size if not self.fail else 0
            return not self.fail

    api = FakeAPI()
    typed_write(api, 123, 0x123456789, PAYLOAD)
    assert api.calls == [(123, 0x123456789, PAYLOAD, 28)]
    for invalid in (b"x" * 27, struct.pack("<7f", 0, 0, 1, 1, -1, 0.1, 0.1), struct.pack("<7f", math.nan, 0, 1, 1, 0.3, 0.1, 0.1)):
        try:
            typed_write(api, 123, 0x123456789, invalid)
            raise AssertionError("Invalid payload accepted")
        except ValueError:
            pass
    assert len(api.calls) == 1

    class FakeBackend:
        def __init__(self):
            self.rows = [1, 2, 3]
            self.writes = []
            self.context = (1, 2)
            self.failure = None
            self.api = FakeAPI()

        def check(self):
            if self.failure == "version":
                raise RuntimeError("changed version")

        def snapshot(self):
            return self.rows, self.context, {}

        def eligible(self, row):
            return True

        def validate(self, row, context):
            if self.failure == "stale" and row == 2:
                raise RuntimeError("stale pointer")
            if self.failure == "despawn" and row == 2:
                raise StaleTarget("target was unloaded")

        def write(self, row):
            self.api.fail = self.failure == "write" and row == 2
            typed_write(self.api, 123, 0x100000 + row * 0x10000, PAYLOAD)
            self.writes.append(row)

    checks = 5
    for failure, expected in (("version", []), ("stale", [1]), ("write", [1]), ("context", [])):
        backend, controller = FakeBackend(), RefreshController()
        controller.enable((1, 2))
        backend.failure = failure
        if failure == "context":
            backend.context = (9, 9)
        try:
            controller.tick(backend)
            raise AssertionError("Failure did not stop refresh")
        except RuntimeError:
            pass
        assert not controller.enabled and backend.writes == expected
        backend.failure = None
        controller.tick(backend)
        assert backend.writes == expected
        checks += 1
    backend, controller = FakeBackend(), RefreshController()
    controller.enable(backend.context)
    backend.failure = "despawn"
    assert controller.tick(backend)[0] == 2
    assert backend.writes == [1, 3] and controller.enabled
    backend.rows = [1, 4, 3]  # A newly loaded animal replaces the stale row.
    assert controller.tick(backend)[0] == 3
    assert backend.writes == [1, 3, 1, 4, 3] and controller.enabled
    checks += 1
    backend, controller = FakeBackend(), RefreshController()
    controller.enable(backend.context)
    assert controller.tick(backend)[0] == 3
    controller.disable()
    assert controller.tick(backend)[0] == 0 and backend.writes == [1, 2, 3]
    requested, stopping = threading.Event(), threading.Event()
    controller.enable_if_requested((1, 2), requested, stopping)
    assert not controller.enabled
    # Exercise the real pre-write identity/resource validator with a fake memory
    # map; no process is opened and no memory API is called.
    row = dict(wrapper="0x20000", character="0x30000", definition="0x40000", hp_178=(20.0, 20.0),
               vtable_rva="0x1a60028", state_cc=123, flags_d4=5,
               definition_path_c0="animations/hp_ragdoll/animals/mexican_bobcat/a.ragdoll")

    class FakeMemory:
        base = 0x140000000

        def __init__(self):
            self.raw = bytearray(0xD8)
            struct.pack_into("<Q", self.raw, 0, 0x30000)
            struct.pack_into("<Q", self.raw, 0x28, 0x40000)
            struct.pack_into("<I", self.raw, 0xCC, 123)
            struct.pack_into("<I", self.raw, 0xD4, 5)
            self.path = row["definition_path_c0"]

        def qword(self, address):
            return {self.base + probe.SINGLETON_RVA: 0x50000,
                    0x50000 + 0xB8: 0x60000, 0x20000: 0x30000,
                    0x30000: self.base + 0x1A60028, 0x40000 + 0xC0: 0x70000}[address]

        def read(self, address, size):
            if address == 0x20000 + 0x178:
                return struct.pack("<2f", 20.0, 20.0)
            return bytes(self.raw) if address == 0x20000 else self.path.encode("ascii").ljust(size, b"\0")

    live = LiveBackend.__new__(LiveBackend)
    live.game = FakeMemory()
    assert live.eligible(row)
    live.validate(row, (0x50000, 0x60000))
    for change in ("pointer", "resource"):
        live.game = FakeMemory()
        if change == "pointer":
            struct.pack_into("<Q", live.game.raw, 0, 0x90000)
        else:
            live.game.path = "animations/hp_ragdoll/animals/bloodhound/a.ragdoll"
        try:
            live.validate(row, (0x50000, 0x60000))
            raise AssertionError("Stale identity/resource accepted")
        except StaleTarget:
            pass
        checks += 1
    live.game = FakeMemory()
    def unreadable(address, size):
        raise OSError("animal was freed")
    live.game.read = unreadable
    try:
        live.validate(row, (0x50000, 0x60000))
        raise AssertionError("Unreadable animal accepted")
    except StaleTarget:
        pass
    checks += 1
    requested.set()
    stopping.set()
    controller.enable_if_requested((1, 2), requested, stopping)
    assert not controller.enabled
    # Engine's confirmed timer path: only positive lifetime decrements; expiry
    # sets target alpha to zero. Repeated finite refresh never needs a reset write.
    lifetime, target_alpha = OUTLINE[4], OUTLINE[3]
    for _ in range(12):
        lifetime = OUTLINE[4]
        lifetime -= INTERVAL
        assert lifetime > 0 and target_alpha == 1
    for _ in range(8):
        if lifetime > 0:
            lifetime -= INTERVAL
            if lifetime <= 0:
                target_alpha = 0
    assert target_alpha == 0 and 0 < OUTLINE[4] <= 1 and len(PAYLOAD) == 28
    print(f"PASS: {checks + 3} targeted checks; no game access or memory writes")


def color_self_test():
    from unittest.mock import patch

    class FakeAPI:
        def __init__(self):
            self.calls = []

        def WriteProcessMemory(self, handle, address, data, size, count):
            self.calls.append((address.value, C.string_at(data, size), size))
            C.cast(count, C.POINTER(C.c_size_t))[0] = size
            return True

    api = FakeAPI()
    backend = LiveBackend.__new__(LiveBackend)
    backend.writer = None
    with patch.dict(globals(), {"K": api}):
        for color in ("white", "blue"):
            backend.writer = None
            backend.set_color(color)
            assert backend.color == color and backend.payload == PAYLOADS[color]
            assert len(backend.payload) == 28
            assert all(abs(a-b) < 1e-6 for a, b in zip(struct.unpack("<7f", backend.payload), OUTLINES[color]))
            backend.writer = 123
            backend.write({"character": "0x123456789"})
            assert api.calls[-1] == (0x123456789 + OUTLINE_OFFSET, PAYLOADS[color], 28)
    try:
        backend.set_color("white")
        raise AssertionError("Color changed while writing was active")
    except RuntimeError:
        pass
    assert backend.color == "blue" and backend.payload == PAYLOADS["blue"]
    with patch.object(probe, "GameMemory", side_effect=AssertionError("Unexpected game access")):
        try:
            LiveBackend("orange")
            raise AssertionError("Unknown color accepted")
        except ValueError:
            pass
    worker = ModWorker()
    assert worker.color == "white"
    worker.requested.set()
    worker.controller.enable((1, 2))
    worker.set_color("blue")
    assert worker.color == "blue" and not worker.requested.is_set() and not worker.controller.enabled
    assert OUTLINES["blue"][3:] == OUTLINES["white"][3:]
    assert PAYLOADS["blue"] != PAYLOADS["white"] and PAYLOAD == PAYLOADS["white"]
    print("PASS: 5 color boundaries; white/blue typed writes, active-write rejection, invalid mode and OFF handoff; fake APIs only")


def single_instance_self_test():
    class FakeAPI:
        def __init__(self, handle, error):
            self.handle, self.error, self.closed, self.created = handle, error, [], []

        def CreateMutexW(self, security, owner, name):
            self.created.append((security, owner, name))
            return self.handle

        def CloseHandle(self, handle):
            self.closed.append(handle)

    first = FakeAPI(100, 0)
    assert acquire_single_instance(first, lambda: first.error) == 100
    assert first.created == [(None, False, MUTEX_NAME)] and not first.closed
    second = FakeAPI(200, 183)
    assert acquire_single_instance(second, lambda: second.error) is None
    assert second.closed == [200]  # Never closes the first instance's handle.
    failed = FakeAPI(None, 5)
    try:
        acquire_single_instance(failed, lambda: failed.error)
        raise AssertionError("Mutex failure allowed startup")
    except RuntimeError:
        pass
    assert not failed.closed and MUTEX_NAME.startswith("Local\\")
    print("PASS: 3 single-instance boundary checks; fake mutex API only")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="COTW 사냥감 윤곽 ON/OFF")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--single-instance-self-test", action="store_true")
    parser.add_argument("--color", choices=("blue", "white"), default="white", help="GUI의 초기 색상 선택")
    arguments = parser.parse_args()
    if arguments.self_test:
        self_test()
        color_self_test()
        single_instance_self_test()
    elif arguments.single_instance_self_test:
        single_instance_self_test()
    else:
        gui(arguments.color)
