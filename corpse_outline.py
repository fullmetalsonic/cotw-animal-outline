"""Leased corpse-only engine outline detour; no game-file changes or threads created.

Code/data allocations deliberately live until the game exits. Never free a
detour while an engine thread could still be executing it.
"""
import hashlib
import math
from pathlib import Path
import struct
import threading

import game_memory as probe
from native_game import NativeAPI, ThreadEntry, rel_call

CALL_RVA = 0x8BE0D6
ORIGINAL_CALL = bytes.fromhex("e8a503deff")
RESET_RVA, UPDATE_RVA, EPILOGUE_RVA = 0x69E480, 0x6B1810, 0x8BE1AB
QPC_IAT_RVA = 0x1920518
VTABLE_RVA = 0x1A60028
CODE_SIZE, HEADER_SIZE, ROW_SIZE, CAPACITY = 4096, 256, 32, 4096
STUB_SHA256 = "4773996da5bb65e414f40e75b0a9f4c1ce37ed124a521c31d2c77ae3b0c5547e"
ALLOCATION_SIZE = 0x22000
MAGIC = b"COTW_CORPSE_V1".ljust(16, b"\0")
LEASE_SECONDS = 0.30
SIGNATURES = {
    0x8BDDD5: bytes.fromhex("488b094885c90f84ca03000080bb5c020000000f85bd030000"),
    RESET_RVA: bytes.fromhex("4883ec2848895c243033db48897c2420488bf9899974240000899964240000c78178240000000080bf"),
    UPDATE_RVA: bytes.fromhex("40534883ec40f30f10a1742400000f57c00f2fe0488bd90f297424300f28d1f3"),
    0x8BE197: bytes.fromhex("488bb424e0000000488bac24d800000083480c40488b9c24e80000004881c4c00000005fc3"),
}


def _address(value):
    return int(value, 16) if isinstance(value, str) else int(value)


def color_rgba(rgb):
    if len(rgb) != 3 or not all(math.isfinite(v) and 0 <= v <= 1 for v in rgb):
        raise ValueError("사체 색상은 0~1 범위의 RGB 세 값이어야 합니다")
    return struct.pack("<4f", *rgb, 1.0)




def _wild_path(path):
    if not isinstance(path, str):
        return False
    path = path.replace("\\", "/").lower()
    if not path.startswith(("animations/hp_ragdoll/animals/", "animations/hp_ragdoll/birds/")) or not path.endswith(".ragdoll"):
        return False
    if any(p in {"..", "dog", "dogs", "retriever", "pointer"} for p in path.split("/")):
        return False
    compact = "".join(c for c in path if c.isalnum())
    return not any(p in compact for p in ("bloodhound", "labrador", "germanshorthairedpointer", "germanpointer"))






class CorpseRenderer:
    def __init__(self, game, writer, *, api=None, code=None):
        self.game, self.writer = game, writer
        self.api = api if api is not None else NativeAPI(game, writer)
        self.code = code if code is not None else Path(__file__).with_name("corpse_stub.bin").read_bytes()
        if len(self.code) != CODE_SIZE or hashlib.sha256(self.code).hexdigest() != STUB_SHA256:
            raise ValueError("사체 훅 바이너리를 확인하지 못했습니다")
        self.code_hash = hashlib.sha256(self.code).digest()
        self.allocation = None
        self.sequence = 0
        self.lock = threading.RLock()

    @property
    def site(self):
        return self.game.base + CALL_RVA

    def _check_signatures(self):
        for rva, expected in SIGNATURES.items():
            if self.api.read(self.game.base + rva, len(expected)) != expected:
                raise RuntimeError("사체 윤곽 엔진 코드가 검증된 버전과 다릅니다")

    def _header(self):
        header = bytearray(HEADER_SIZE)
        header[:16] = MAGIC
        struct.pack_into("<II5Q", header, 16, 1, CAPACITY, self.game.base,
                         self.game.base + QPC_IAT_RVA, self.game.base + RESET_RVA,
                         self.game.base + UPDATE_RVA, self.game.base + EPILOGUE_RVA)
        struct.pack_into("<3Q", header, 104, self.game.base + VTABLE_RVA, self.site, ALLOCATION_SIZE)
        header[128:160] = self.code_hash
        header[160:192] = bytes.fromhex(probe.EXPECTED_SHA256)
        return bytes(header)

    def _verify_owned(self, allocation):
        if not 0x10000 <= allocation <= 0x7FFFFFFFFFFF - ALLOCATION_SIZE or allocation & 0xFFFF:
            raise RuntimeError("기존 사체 훅 위치가 유효하지 않습니다")
        actual = self.api.read(allocation + CODE_SIZE, HEADER_SIZE)
        expected = self._header()
        # Only sequence/deadline/count/RGBA change after installation.
        if actual[:64] != expected[:64] or actual[104:] != expected[104:] or self.api.read(allocation, CODE_SIZE) != self.code:
            raise RuntimeError("기존 사체 훅 소유권과 코드를 확인하지 못했습니다")
        self.sequence = struct.unpack_from("<Q", actual, 64)[0]

    def _install(self):
        self._check_signatures()
        if hashlib.sha256(self.game.exe.read_bytes()).hexdigest() != probe.EXPECTED_SHA256:
            raise RuntimeError("지원하지 않는 게임 파일이어서 사체 훅을 설치하지 않았습니다")
        current = self.api.read(self.site, 5)
        if current != ORIGINAL_CALL:
            if current[:1] != b"\xe8":
                raise RuntimeError("사체 호출 코드가 다른 프로그램에 의해 변경되었습니다")
            target = self.site + 5 + struct.unpack("<i", current[1:])[0]
            self._verify_owned(target)
            self.allocation = target
            self.disable()
            return
        allocation = self.api.allocate_near(self.site)
        self.api.write(allocation, self.code)
        self.api.write(allocation + CODE_SIZE, self._header())
        self._verify_owned(allocation)
        self.api.protect(allocation, CODE_SIZE, 0x20)  # RX code, separate RW data
        self.api.flush(allocation, CODE_SIZE)
        patch = rel_call(self.site, allocation)
        with self.api.frozen_threads(self.site, 5):
            self._check_signatures()
            if self.api.read(self.site, 5) != ORIGINAL_CALL:
                raise RuntimeError("설치 중 사체 호출 코드가 바뀌었습니다")
            old_protection = self.api.protect(self.site, 5, 0x40)
            touched = False
            try:
                touched = True
                self.api.write(self.site, patch)
                if self.api.read(self.site, 5) != patch:
                    raise OSError("사체 호출 코드 기록 검증에 실패했습니다")
                self.api.flush(self.site, 5)
                self.api.protect(self.site, 5, old_protection)
            except Exception as error:
                if touched:
                    try:
                        self.api.protect(self.site, 5, 0x40)
                        self.api.write(self.site, ORIGINAL_CALL)
                        if self.api.read(self.site, 5) != ORIGINAL_CALL:
                            raise OSError("원본 호출 코드 복원 검증 실패")
                        self.api.flush(self.site, 5)
                        self.api.protect(self.site, 5, old_protection)
                    except Exception as rollback_error:
                        raise RuntimeError("사체 훅 설치와 원본 복원에 실패했습니다. 게임을 종료하세요") from rollback_error
                raise RuntimeError("사체 훅 설치 실패: 원본 호출 코드를 복원했습니다") from error
        self.allocation = allocation

    def _row(self, row):
        if not _wild_path(row.get("definition_path_c0")) or _address(row["vtable_rva"]) != VTABLE_RVA:
            return None
        wrapper, character, definition = (_address(row[k]) for k in ("wrapper", "character", "definition"))
        raw = self.api.read(wrapper, 0x260)
        state = struct.unpack_from("<I", raw, 0xCC)[0]
        health = struct.unpack_from("<f", raw, 0x17C)[0]
        if (struct.unpack_from("<Q", raw)[0] != character or struct.unpack_from("<Q", raw, 0x28)[0] != definition
                or state != row["state_cc"] or state == 0xDEADBEEF or not raw[0xD4] & 4
                or raw[0x25C] or not math.isfinite(health) or health > 0):
            return None
        if struct.unpack("<Q", self.api.read(character, 8))[0] != self.game.base + VTABLE_RVA:
            return None
        if self.api.read(character + 0x220, 2) != b"\0\0" or self.api.read(character + 0x21C, 1) != b"\x01":
            return None
        count = struct.unpack("<I", self.api.read(character + 0x1098, 4))[0]
        if not 1 <= count <= 64:
            return None
        path_pointer = struct.unpack("<Q", self.api.read(definition + 0xC0, 8))[0]
        path = self.api.read(path_pointer, 240).split(b"\0", 1)[0].decode("ascii")
        if path != row["definition_path_c0"] or not _wild_path(path):
            return None
        return struct.pack("<QQQII", wrapper, character, definition, state, 0)

    def _publish(self, packed, rgba, deadline):
        header = self.allocation + CODE_SIZE
        # An odd sequence is disabled. Every failure after it stays disabled;
        # the last completed lease also expires without this process running.
        self.sequence = ((self.sequence + 2) & 0xFFFFFFFFFFFFFFFE) or 2
        self.api.write(header + 64, struct.pack("<Q", self.sequence - 1))
        try:
            if packed:
                self.api.write(header + HEADER_SIZE, packed)
            self.api.write(header + 72, struct.pack("<QQ", deadline, len(packed) // ROW_SIZE) + rgba)
            self.api.write(header + 64, struct.pack("<Q", self.sequence))
        except Exception:
            # Keep the sequence odd even if a final write partially succeeded.
            try:
                self.api.write(header + 72, bytes(16))
            except Exception:
                pass
            raise

    def publish(self, validated_dead_rows, colorRGB=(1.0, 0.35, 0.0)):
        rgba = color_rgba(colorRGB)
        with self.lock:
            packed, seen = [], set()
            for row in validated_dead_rows:
                try:
                    item = self._row(row)
                except (OSError, ValueError, UnicodeError, struct.error):
                    continue
                if item is not None and item[:16] not in seen:
                    packed.append(item); seen.add(item[:16])
            if len(packed) > CAPACITY:
                self.disable()
                raise ValueError("사체 목록이 검증된 크기를 초과했습니다")
            if not packed:
                self.disable()
                return 0
            if self.allocation is None:
                self._install()
            self._check_signatures()
            if self.api.read(self.site, 5) != rel_call(self.site, self.allocation):
                raise RuntimeError("사체 훅 호출 코드가 바뀌었습니다")
            now, frequency = self.api.clock()
            deadline = now + int(LEASE_SECONDS * frequency)
            self._publish(b"".join(packed), rgba, deadline)
            return len(packed)

    def disable(self):
        with self.lock:
            if self.allocation is not None:
                try:
                    self._publish(b"", bytes(16), 0)
                except OSError:
                    if self.api.is_running():
                        raise
                    # The game has exited; its allocation no longer exists.
                    self.allocation = None

    def close(self):
        self.disable()  # Never unpatch/free live code; expiration restores play.
