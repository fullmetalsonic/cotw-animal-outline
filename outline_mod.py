"""Temporary, single-player outline refresh; never patches game files or code."""
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


class StaleTarget(RuntimeError):
    """A single animal no longer matches its snapshot; never authorizes a write."""


class LiveBackend:
    def __init__(self, color="white"):
        self.writer = None
        self.set_color(color)
        self.game = probe.GameMemory()
        self.file_stamp = self._stamp()

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

    def eligible(self, row):
        return (int(row["vtable_rva"], 16) in VERIFIED_WILD_VTABLE_RVAS
                and wild_resource_path(row.get("definition_path_c0"))
                and bool(row["flags_d4"] & 4) and row["state_cc"] != 0xDEADBEEF)

    def validate(self, row, context):
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
            if not self.eligible(row):
                raise StaleTarget("검증되지 않은 사냥감은 갱신하지 않습니다")
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

    def close(self):
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

    def tick(self, backend):
        try:
            backend.check()
            rows, context, summary = backend.snapshot()
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
        self.stopping = threading.Event()
        self.messages = queue.Queue()
        self.controller = RefreshController()

    def off(self):
        self.requested.clear()
        self.controller.disable()

    def close(self):
        self.off()
        self.stopping.set()

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
                        self.messages.put(("연결됨 · 모드 OFF", 0, last_error or "사냥감 윤곽을 켤 준비가 되었습니다."))
                    if self.requested.is_set():
                        if not self.controller.enabled:
                            rows, context, summary = backend.snapshot()
                            with self.color_lock:
                                backend.stop_writing()
                                backend.set_color(self.color)
                                backend.start_writing()
                                self.controller.enable_if_requested(context, self.requested, self.stopping)
                        if self.controller.enabled:
                            count, summary = self.controller.tick(backend)
                            last_error = None
                            self.messages.put(("모드 ON", count, f"로드된 사냥감의 {COLOR_LABELS[backend.color]} 윤곽을 갱신하고 있습니다."))
                    else:
                        backend.stop_writing()
                        if time.monotonic() - last_poll >= 1:
                            rows, context, summary = backend.snapshot()
                            count = sum(backend.eligible(row) for row in rows)
                            self.messages.put(("연결됨 · 모드 OFF", count, last_error or "윤곽 갱신이 중지되었습니다. 임시 윤곽은 게임 진행 중 잠시 후 사라집니다."))
                            last_poll = time.monotonic()
                except Exception as error:
                    was_on = self.requested.is_set() or self.controller.enabled
                    if was_on:
                        last_error = str(error)
                    self.off()
                    if backend:
                        backend.close()
                        backend = None
                    self.messages.put(("오류 · 모드 OFF" if was_on else "게임 연결 대기 · 모드 OFF", 0, str(error)))
                    self.stopping.wait(1)
                self.stopping.wait(INTERVAL)
        finally:
            self.controller.disable()
            if backend:
                backend.close()


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
    from tkinter import ttk
    shell = C.WinDLL("shell32")
    shell.SetCurrentProcessExplicitAppUserModelID.argtypes = [W.LPCWSTR]
    shell.SetCurrentProcessExplicitAppUserModelID.restype = C.c_long
    shell.SetCurrentProcessExplicitAppUserModelID("Local.COTW.WildAnimalOutlineMod")
    root = tk.Tk()
    root.title("COTW 사냥감 윤곽 모드")
    root.geometry("550x530")
    root.minsize(450, 510)
    panel = ttk.Frame(root, padding=22)
    panel.pack(fill="both", expand=True)
    ttk.Label(panel, text="사냥감 기본 윤곽", font=("맑은 고딕", 17, "bold")).pack(anchor="w")
    ttk.Label(panel, text="대상 빌드: 26051119 · 싱글플레이 전용").pack(anchor="w", pady=(5, 18))
    status = tk.StringVar(value="게임 연결 확인 중 · 모드 OFF")
    count = tk.StringVar(value="표시 대상: 0마리")
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

    panel.bind("<Configure>", resize)
    worker.start()

    def poll():
        nonlocal update_running, release_link
        for button in color_buttons:
            button.state(["disabled"] if worker.requested.is_set() or worker.controller.enabled else ["!disabled"])
        latest = None
        while True:
            try:
                latest = worker.messages.get_nowait()
            except queue.Empty:
                break
        if latest and not (latest[0] == "모드 ON" and not worker.requested.is_set()):
            status.set(latest[0])
            count.set(f"표시 대상: {latest[1]}마리")
            detail.set(latest[2])
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
    row = dict(wrapper="0x20000", character="0x30000", definition="0x40000",
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
