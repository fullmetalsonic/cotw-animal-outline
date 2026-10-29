"""Keep the local dog's native outline independent of HideAllClues.

Only the HideAllClues getter's return at the dog-specific call site is leased.
Native outline enable/color, world restrictions and screen metrics still run.
"""
import hashlib
from pathlib import Path
import struct
import threading

import game_memory as probe
from native_game import ALLOCATION_SIZE, NativeAPI, rel_call

CALL_RVA, ORIGINAL_RVA = 0x6A7E66, 0xAE93C0
ORIGINAL_CALL = bytes.fromhex("e855154400")
WORLD_RVA, LOCAL_RVA, ENTITY_RVA = 0x27C5DC8, 0x27F1478, 0x27C5D50
SETTINGS_RVA, QPC_IAT_RVA = 0x2801460, 0x1920518
CHAR_VTABLE_RVA, PLAYER_VTABLE_RVA = 0x1A60028, 0x1EE24A0
CODE_SIZE, HEADER_SIZE, STATS_SIZE = 4096, 320, 64
MAGIC = b"COTW_PETBLUE_V1".ljust(16, b"\0")
LEASE_SECONDS = .30
STUB_SHA256 = "8de7c7051b1ed1a198e7ffc396e8450f7473f3cda37bac0917a25117ed23463e"
SIGNATURES = {
    0x6A7E30: bytes.fromhex("40534883ec50488bd90f29742440488b0d1b961502ba910000000f28f1e86e15440085c00f84a3000000488b0dff951502bac4000000"),
    0x6A7E6B: bytes.fromhex("85c00f858a000000488b0d4edf1102e8c18e2b0084c0757a"),
    0xAE9437: bytes.fromhex("498b82201000004863ca8b0488c3"),
    0x68C4C0: bytes.fromhex("4883b9d82a0000000f95c0c3"),
}


class TransientPetState(RuntimeError):
    """No stable local dog binding: expire, wait and re-read without guessing."""


class PetOutlineKeeper:
    def __init__(self, game, writer, *, api=None, code=None):
        self.game, self.writer = game, writer
        self.api = api if api is not None else NativeAPI(game, writer)
        self.code = code if code is not None else Path(__file__).with_name("pet_stub.bin").read_bytes()
        if len(self.code) != CODE_SIZE or hashlib.sha256(self.code).hexdigest() != STUB_SHA256:
            raise ValueError("반려견 윤곽 모드 바이너리를 확인하지 못했습니다")
        self.allocation, self.sequence, self.last_binding = None, 0, None
        self.lock = threading.RLock()

    @property
    def site(self):
        return self.game.base+CALL_RVA

    def _u32(self, address):
        return struct.unpack("<I", self.api.read(address, 4))[0]

    def _qword(self, address):
        return struct.unpack("<Q", self.api.read(address, 8))[0]

    def _header(self):
        result = bytearray(HEADER_SIZE)
        result[:16] = MAGIC
        struct.pack_into("<II5Q", result, 16, 1, 0, self.game.base,
                         self.game.base+QPC_IAT_RVA, self.game.base+ORIGINAL_RVA,
                         self.game.base+LOCAL_RVA, self.game.base+ENTITY_RVA)
        result[128:160] = hashlib.sha256(self.code).digest()
        result[160:192] = bytes.fromhex(probe.EXPECTED_SHA256)
        struct.pack_into("<6Q", result, 192, ALLOCATION_SIZE, self.site,
                         self.game.base+CHAR_VTABLE_RVA, self.game.base+PLAYER_VTABLE_RVA,
                         self.game.base+WORLD_RVA, self.game.base+SETTINGS_RVA)
        return bytes(result)

    def _verify_owned(self, allocation):
        if not 0x10000 <= allocation <= 0x7FFFFFFFFFFF-ALLOCATION_SIZE or allocation & 0xFFFF:
            raise RuntimeError("기존 반려견 윤곽 모드 위치가 유효하지 않습니다")
        actual = self.api.read(allocation+CODE_SIZE, HEADER_SIZE)
        expected = self._header()
        if (actual[:64] != expected[:64] or actual[128:256] != expected[128:256]
                or self.api.read(allocation, CODE_SIZE) != self.code):
            raise RuntimeError("기존 반려견 윤곽 모드 소유권을 확인하지 못했습니다")
        self.sequence = struct.unpack_from("<Q", actual, 64)[0]

    def _check_signatures(self):
        for rva, expected in SIGNATURES.items():
            if self.api.read(self.game.base+rva, len(expected)) != expected:
                raise RuntimeError("반려견 윤곽 코드가 검증된 버전과 다릅니다")
        current = self.api.read(self.site, 5)
        if current != ORIGINAL_CALL:
            if current[:1] != b"\xe8":
                raise RuntimeError("반려견 윤곽 코드가 다른 프로그램에 의해 변경되었습니다")
            self._verify_owned(self.site+5+struct.unpack("<i", current[1:])[0])

    def _install(self):
        self._check_signatures()
        if hashlib.sha256(self.game.exe.read_bytes()).hexdigest() != probe.EXPECTED_SHA256:
            raise RuntimeError("지원하지 않는 게임 파일입니다")
        current = self.api.read(self.site, 5)
        if current != ORIGINAL_CALL:
            allocation = self.site+5+struct.unpack("<i", current[1:])[0]
            self._verify_owned(allocation)
            self.allocation = allocation
            self.disable()
            return
        allocation = self.api.allocate_near(self.site)
        self.api.write(allocation, self.code)
        self.api.write(allocation+CODE_SIZE, self._header()+bytes(STATS_SIZE))
        self._verify_owned(allocation)
        self.api.protect(allocation, CODE_SIZE, 0x20)
        self.api.flush(allocation, CODE_SIZE)
        patch = rel_call(self.site, allocation)
        with self.api.frozen_threads(self.site, 5):
            self._check_signatures()
            if self.api.read(self.site, 5) != ORIGINAL_CALL:
                raise RuntimeError("설치 중 반려견 윤곽 코드가 바뀌었습니다")
            old = self.api.protect(self.site, 5, 0x40)
            try:
                self.api.write(self.site, patch)
                if self.api.read(self.site, 5) != patch:
                    raise OSError("반려견 윤곽 코드 기록 검증 실패")
                self.api.flush(self.site, 5)
                self.api.protect(self.site, 5, old)
            except Exception as error:
                try:
                    self.api.protect(self.site, 5, 0x40)
                    self.api.write(self.site, ORIGINAL_CALL)
                    if self.api.read(self.site, 5) != ORIGINAL_CALL:
                        raise OSError("원본 코드 복원 검증 실패")
                    self.api.flush(self.site, 5)
                    self.api.protect(self.site, 5, old)
                except Exception as rollback_error:
                    raise RuntimeError("반려견 윤곽 설치와 복원에 실패했습니다. 게임을 종료하세요") from rollback_error
                raise RuntimeError("반려견 윤곽 설치 실패: 원본 코드를 복원했습니다") from error
        self.allocation = allocation

    def _local(self):
        # Reuse the project's closed local-character/generation-map contract.
        # No NinjaMode instance or ninja lease is created or modified.
        from ninja_mode import NinjaMode, TransientNinjaState
        try:
            result = NinjaMode._binding(self)
        except TransientNinjaState as error:
            raise TransientPetState(str(error)) from error
        manager = self._qword(self.game.base+LOCAL_RVA)
        slot = self._qword(manager+0x60)
        if self._qword(slot+0x170) != result["character"]:
            raise TransientPetState("로컬 플레이어 연결이 변경 중입니다")
        result["slot"] = slot
        result["owner_id"] = self.api.read(slot+0x148, 1)[0]
        owner_component = self._qword(result["character"]+0x2AD0)
        if not owner_component or self._qword(owner_component+0x10) != result["player"]:
            raise TransientPetState("반려견 주인 연결이 변경 중입니다")
        result["owner_component"] = owner_component
        # A347F0's native owner-ID lookup must resolve uniquely to localSlot.
        begin, end = self._qword(manager+0x40), self._qword(manager+0x48)
        if not begin or not begin <= end <= begin+8*64 or (end-begin) % 8:
            raise RuntimeError("플레이어 목록이 유효하지 않습니다")
        slots = struct.unpack("<"+"Q"*((end-begin)//8), self.api.read(begin, end-begin))
        owners = [s for s in slots if s and self.api.read(s+0x148, 1)[0] == result["owner_id"]]
        if owners != [slot]:
            raise TransientPetState("반려견 주인을 하나로 확인하지 못했습니다")
        return result

    def _pet_candidate(self, character, owner_id):
        # Pool discovery can overlap an unrelated animal's destruction. An
        # unreadable row is never accepted; the eventual pet is revalidated.
        try:
            if self._qword(character) != self.game.base+CHAR_VTABLE_RVA:
                return None
            dog = self._qword(character+0x2AD8)
            if not dog or self._qword(dog+0x18) != character:
                return None
            meta = self._qword(dog+0xB0)
            if not meta:
                return None
            actual_owner, active = self.api.read(meta, 2)
            return (dog, meta) if actual_owner == owner_id and active else None
        except OSError:
            return None

    def _binding(self):
        local = self._local()
        pool, mapping = local["pool"], local["mapping"]
        nodes = self._qword(pool)
        count = struct.unpack("<H", self.api.read(pool+0x1A, 2))[0]
        if not nodes or not 0 < count <= 16384:
            raise RuntimeError("AI 입력 목록이 유효하지 않습니다")
        records = self.api.read(nodes, count*0x180)
        capacity = self._u32(pool+0x120)
        pets = []
        for offset in range(0, len(records), 0x180):
            if struct.unpack_from("<I", records, offset+0x170)[0] != 1 or not records[offset+0x17C] & 1:
                continue
            character = struct.unpack_from("<Q", records, offset+0xB8)[0]
            if not character or character == local["character"]:
                continue
            candidate = self._pet_candidate(character, local["owner_id"])
            if candidate is None:
                continue
            dog, meta = candidate
            handle = self._u32(character+0x2098)
            index = handle >> 16
            source = nodes+offset
            if (not handle & 0xFFFF or index >= capacity
                    or struct.unpack_from("<H", records, offset+0x174)[0] != index):
                raise TransientPetState("반려견 AI 입력이 변경 중입니다")
            entry = self._u32(mapping+index*4)
            if entry & 0xFFFF != handle & 0xFFFF or nodes+(entry >> 16)*0x180 != source:
                raise TransientPetState("반려견 AI 입력 세대가 변경 중입니다")
            pets.append(dict(dog_character=character, dog=dog, dog_source=source, dog_handle=handle, meta=meta))
        if len(pets) != 1:
            raise TransientPetState("활성 반려견 연결을 기다리고 있습니다")
        pet = pets[0]
        if self._local() != local or self._qword(pool) != nodes or struct.unpack("<H", self.api.read(pool+0x1A, 2))[0] != count:
            raise TransientPetState("반려견 목록이 변경 중입니다")
        # Fresh pair/owner/handle checks precede every lease publication.
        c, d, s, h = (pet[k] for k in ("dog_character", "dog", "dog_source", "dog_handle"))
        if (self._qword(c+0x2AD8) != d or self._qword(d+0x18) != c or self._qword(d+0xB0) != pet["meta"]
                or self.api.read(pet["meta"], 1)[0] != local["owner_id"] or not self.api.read(pet["meta"]+1, 1)[0]
                or self._u32(c+0x2098) != h or self._qword(s+0xB8) != c
                or self._u32(s+0x170) != 1 or not self.api.read(s+0x17C, 1)[0] & 1
                or self._u32(mapping+(h >> 16)*4) != entry):
            raise TransientPetState("반려견 연결이 변경 중입니다")
        return dict(**local, **pet)

    def _publish(self, binding, deadline):
        header = self.allocation+CODE_SIZE
        self.sequence = ((self.sequence+2) & 0xFFFFFFFFFFFFFFFE) or 2
        self.api.write(header+64, struct.pack("<Q", self.sequence-1))
        try:
            primary = [deadline]+([binding[k] for k in ("character", "player", "handle", "pool", "mapping", "slot")] if binding else [0]*6)
            pet = [binding[k] for k in ("dog_character", "dog", "dog_source", "dog_handle", "owner_id", "meta", "source", "owner_component")] if binding else [0]*8
            self.api.write(header+72, struct.pack("<7Q", *primary))
            self.api.write(header+256, struct.pack("<8Q", *pet))
            self.api.write(header+64, struct.pack("<Q", self.sequence))
        except Exception:
            try:
                self.api.write(header+72, bytes(8))
            except OSError:
                pass
            raise

    def publish(self):
        with self.lock:
            try:
                self._check_signatures()
                binding = self._binding()
                if self.allocation is None:
                    self._install()
                    binding = self._binding()
                if self.api.read(self.site, 5) != rel_call(self.site, self.allocation):
                    raise RuntimeError("반려견 윤곽 호출 코드가 바뀌었습니다")
                now, frequency = self.api.clock()
                self._publish(binding, now+int(LEASE_SECONDS*frequency))
                self.last_binding = binding
                return 1
            except Exception as error:
                try:
                    self.disable()
                except OSError:
                    if isinstance(error, TransientPetState):
                        raise
                raise

    def disable(self):
        with self.lock:
            if self.allocation is not None:
                try:
                    self._publish(None, 0)
                except OSError:
                    if self.api.is_running():
                        raise
                    self.allocation = None
            self.last_binding = None

    def close(self):
        self.disable()  # Executable memory remains valid until game exit.

    def read_stats(self):
        with self.lock:
            if self.allocation is None:
                return dict(total=0, filtered=0, fallback=0)
            values = struct.unpack("<8Q", self.api.read(self.allocation+CODE_SIZE+HEADER_SIZE, STATS_SIZE))
            return dict(zip(("total", "filtered", "fallback", "original_value", "returned_value", "dog", "qpc", "sequence"), values))
