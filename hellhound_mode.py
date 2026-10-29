"""Leased local Retriever eligibility and native whole-corpse relocation.

Native pickup always runs once; only a validated dead class2..9 is relocated.
Actual animal class, health, weight, rewards and save fields are untouched.
"""
from contextlib import ExitStack
import hashlib
import math
from pathlib import Path
import struct
import threading

import game_memory as probe
from native_game import ALLOCATION_SIZE, NativeAPI, rel_call
from pet_outline import (PetOutlineKeeper, TransientPetState, WORLD_RVA,
                         LOCAL_RVA, ENTITY_RVA, QPC_IAT_RVA,
                         CHAR_VTABLE_RVA, PLAYER_VTABLE_RVA)

GATE_RVA, REJECT_RVA = 0x8F1DB7, 0x8F20EB
ORIGINAL_GATE = bytes.fromhex("488b4228807861010f8526030000")
PICKUP_CALL_RVA, PICKUP_FUNCTION_RVA = 0x6CB25F, 0x6BDDB0
ORIGINAL_PICKUP_CALL = bytes.fromhex("e84c2bffff")
CHAR_SETTER_RVA, RAGDOLL_SETTER_RVA, CHAR_INTERFACE_RVA = 0x6A47E0, 0x334F80, 0x1A601A0
JOB_VTABLE_RVA, HOST_RVA = 0x1DEF1D8, 0x27C5DB8
CODE_SIZE, PICKUP_OFFSET, HEADER_SIZE, STATS_SIZE = 8192, 4096, 384, 160
MAGIC = b"COTW_HELLHND_V2".ljust(16, b"\0")
LEASE_SECONDS = .30
STUB_SHA256 = "9e1fc7ba68afbdaec1a1c8f2593f52661053682e4bc33f6cd0cf7e34e7d7cfec"
SIGNATURES = {
    0x5DAB92: bytes.fromhex("e8a90e3200"),  # Reject leftover V1 weight hooks; never patch this site.
    0x8F1DC5: bytes.fromhex("488b1a4885db0f841a030000488bcb"),
    0x6CB24F: bytes.fromhex("4c8d0d9af3ed014c8bc3488bd7498bcf"),
    0x6CB264: bytes.fromhex("488bcb"),
    PICKUP_FUNCTION_RVA: bytes.fromhex("40534883ec60c60101498bd8410f10014c8d442420488bcb410f1049100f11442420410f1041200f114c2430410f1049300f114424400f114c2450e8b013feff4533c0488d0d96bf3a01418d5012e88d616c00488d54247089442470488bcbe8dcadfdff4883c4605bc3"),
    CHAR_SETTER_RVA: bytes.fromhex("48895c24184889742420574881ec800000000f1002488db15c220000488bda48"),
    RAGDOLL_SETTER_RVA: bytes.fromhex("405355565741564881ecb0060000488b05c3af2d024833c448898424a0060000"),
}


class TransientHellhoundState(RuntimeError):
    """Expire both hooks and wait for a fresh local Retriever job binding."""


class HellhoundMode(PetOutlineKeeper):
    # Only the existing read-only local/pet binding helpers are inherited.
    def __init__(self, game, writer, *, api=None, code=None):
        self.game, self.writer = game, writer
        self.api = api if api is not None else NativeAPI(game, writer)
        self.code = code if code is not None else Path(__file__).with_name("hellhound_stub.bin").read_bytes()
        if len(self.code) != CODE_SIZE or hashlib.sha256(self.code).hexdigest() != STUB_SHA256:
            raise ValueError("헬하운드 모드 바이너리를 확인하지 못했습니다")
        self.allocation, self.sequence, self.last_binding = None, 0, None
        self.lock = threading.RLock()

    @property
    def site(self):
        return self.game.base+GATE_RVA

    @property
    def pickup_site(self):
        return self.game.base+PICKUP_CALL_RVA

    def _patches(self, allocation):
        gate = (rel_call(self.site, allocation)+b"\x0f\x85"
                +struct.pack("<i", self.game.base+REJECT_RVA-(self.site+11))+b"\x90"*3)
        return gate, rel_call(self.pickup_site, allocation+PICKUP_OFFSET)

    def _header(self):
        result = bytearray(HEADER_SIZE)
        result[:16] = MAGIC
        struct.pack_into("<II5Q", result, 16, 2, 0, self.game.base,
                         self.game.base+QPC_IAT_RVA, self.game.base+PICKUP_FUNCTION_RVA,
                         self.game.base+LOCAL_RVA, self.game.base+ENTITY_RVA)
        result[128:160] = hashlib.sha256(self.code).digest()
        result[160:192] = bytes.fromhex(probe.EXPECTED_SHA256)
        struct.pack_into("<8Q", result, 192, ALLOCATION_SIZE, self.site,
                         self.game.base+CHAR_VTABLE_RVA, self.game.base+PLAYER_VTABLE_RVA,
                         self.game.base+WORLD_RVA, self.game.base+HOST_RVA,
                         self.game.base+JOB_VTABLE_RVA, self.game.base+CHAR_SETTER_RVA)
        struct.pack_into("<2Q", result, 336, self.game.base+RAGDOLL_SETTER_RVA,
                         self.game.base+CHAR_INTERFACE_RVA)
        return bytes(result)

    def _verify_owned(self, allocation):
        if not 0x10000 <= allocation <= 0x7FFFFFFFFFFF-ALLOCATION_SIZE or allocation & 0xFFFF:
            raise RuntimeError("기존 헬하운드 모드 위치가 유효하지 않습니다")
        actual = self.api.read(allocation+CODE_SIZE, HEADER_SIZE)
        expected = self._header()
        if (actual[:64] != expected[:64] or actual[128:256] != expected[128:256]
                or actual[336:352] != expected[336:352] or actual[368:] != expected[368:]
                or self.api.read(allocation, CODE_SIZE) != self.code):
            raise RuntimeError("기존 헬하운드 모드 소유권을 확인하지 못했습니다")
        self.sequence = struct.unpack_from("<Q", actual, 64)[0]

    def _check_signatures(self):
        for rva, expected in SIGNATURES.items():
            if self.api.read(self.game.base+rva, len(expected)) != expected:
                raise RuntimeError("헬하운드 코드가 검증된 버전과 다릅니다")
        gate = self.api.read(self.site, len(ORIGINAL_GATE))
        pickup = self.api.read(self.pickup_site, 5)
        if gate == ORIGINAL_GATE and pickup == ORIGINAL_PICKUP_CALL:
            return None
        if gate[:1] == b"\xe8":
            allocation = self.site+5+struct.unpack("<i", gate[1:5])[0]
            if (gate, pickup) == self._patches(allocation):
                self._verify_owned(allocation)
                return allocation
        raise RuntimeError("헬하운드 코드가 다른 프로그램에 의해 변경되었습니다")

    def _install(self):
        owned = self._check_signatures()
        if hashlib.sha256(self.game.exe.read_bytes()).hexdigest() != probe.EXPECTED_SHA256:
            raise RuntimeError("지원하지 않는 게임 파일입니다")
        if owned is not None:
            self.allocation = owned
            self.disable()
            return
        allocation = self.api.allocate_near(self.site)
        patches = self._patches(allocation)  # Both relative calls must be in range.
        self.api.write(allocation, self.code)
        self.api.write(allocation+CODE_SIZE, self._header()+bytes(STATS_SIZE))
        self._verify_owned(allocation)
        self.api.protect(allocation, CODE_SIZE, 0x20)
        self.api.flush(allocation, CODE_SIZE)
        sites = ((self.site, ORIGINAL_GATE, patches[0]),
                 (self.pickup_site, ORIGINAL_PICKUP_CALL, patches[1]))
        # Nested suspension counts keep every thread paused while both sites
        # are checked, patched or rolled back; each scope resumes its own count.
        with ExitStack() as stack:
            for site, original, _ in sites:
                stack.enter_context(self.api.frozen_threads(site, len(original)))
            if self._check_signatures() is not None:
                raise RuntimeError("설치 중 헬하운드 코드가 바뀌었습니다")
            protections = []
            try:
                for site, original, _ in sites:
                    protections.append(self.api.protect(site, len(original), 0x40))
                for site, original, patch in sites:
                    self.api.write(site, patch)
                    if self.api.read(site, len(original)) != patch:
                        raise OSError("헬하운드 코드 기록 검증 실패")
                    self.api.flush(site, len(original))
                for (site, original, _), old in zip(sites, protections):
                    self.api.protect(site, len(original), old)
            except Exception as error:
                try:
                    for index, (site, original, _) in enumerate(sites):
                        if index >= len(protections):
                            continue  # This site's protection/write was never changed.
                        self.api.protect(site, len(original), 0x40)
                        self.api.write(site, original)
                        if self.api.read(site, len(original)) != original:
                            raise OSError("원본 코드 복원 검증 실패")
                        self.api.flush(site, len(original))
                        self.api.protect(site, len(original), protections[index])
                except Exception as rollback_error:
                    raise RuntimeError("헬하운드 설치와 복원에 실패했습니다. 게임을 종료하세요") from rollback_error
                raise RuntimeError("헬하운드 설치 실패: 원본 코드를 복원했습니다") from error
        self.allocation = allocation

    def _binding(self):
        try:
            local = PetOutlineKeeper._binding(self)
            dog = local["dog"]
            begin, end = self._qword(dog+0xC8), self._qword(dog+0xD0)
            if not begin or not begin <= end <= begin+32*8 or (end-begin) % 8:
                raise TransientHellhoundState("리트리버 작업 연결을 기다리고 있습니다")
            jobs = struct.unpack("<"+"Q"*((end-begin)//8), self.api.read(begin, end-begin))
            matches = []
            for job in jobs:
                try:
                    if job and self._qword(job) == self.game.base+JOB_VTABLE_RVA and self._qword(job+0x18) == dog:
                        matches.append(job)
                except OSError:
                    continue
            if len(matches) != 1:
                raise TransientHellhoundState("활성 리트리버 작업을 기다리고 있습니다")
            job = matches[0]
            host = self._qword(self.game.base+HOST_RVA)
            if not host:
                raise TransientHellhoundState("사냥개 관리자 연결을 기다리고 있습니다")
            if (self._qword(dog+0xC8) != begin or self._qword(dog+0xD0) != end
                    or self.api.read(begin, end-begin) != struct.pack("<"+"Q"*len(jobs), *jobs)
                    or self._qword(job) != self.game.base+JOB_VTABLE_RVA or self._qword(job+0x18) != dog
                    or PetOutlineKeeper._binding(self) != local):
                raise TransientHellhoundState("리트리버 연결이 변경 중입니다")
            return dict(**local, job=job, dog_manager=host+0xEBF8)
        except (TransientPetState, OSError) as error:
            raise TransientHellhoundState(str(error)) from error

    def _publish(self, binding, deadline):
        header = self.allocation+CODE_SIZE
        self.sequence = ((self.sequence+2) & 0xFFFFFFFFFFFFFFFE) or 2
        self.api.write(header+64, struct.pack("<Q", self.sequence-1))
        try:
            primary = [deadline]+([binding[k] for k in ("character", "player", "handle", "pool", "mapping", "slot")] if binding else [0]*6)
            pet = [binding[k] for k in ("dog_character", "dog", "dog_source", "dog_handle", "owner_id", "meta", "source", "owner_component")] if binding else [0]*8
            job = [binding[k] for k in ("job", "dog_manager")] if binding else [0]*2
            self.api.write(header+72, struct.pack("<7Q", *primary))
            self.api.write(header+256, struct.pack("<8Q", *pet))
            self.api.write(header+320, struct.pack("<2Q", *job))
            self.api.write(header+352, struct.pack("<3fI", *binding["destination"], 1) if binding else bytes(16))
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
                owned = self._check_signatures()
                binding = self._binding()
                if self.allocation is None:
                    self._install()
                    binding = self._binding()
                elif owned != self.allocation:
                    raise RuntimeError("헬하운드 호출 코드가 바뀌었습니다")
                binding["destination"] = self._destination(binding)
                now, frequency = self.api.clock()
                self._publish(binding, now+int(LEASE_SECONDS*frequency))
                self.last_binding = binding
                return 1
            except Exception as error:
                try:
                    self.disable()
                except OSError:
                    if isinstance(error, TransientHellhoundState):
                        raise  # A failed cleanup write is fatal, never waiting.
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

    def _destination(self, binding):
        matrix = struct.unpack("<16f", self.api.read(binding["character"]+0x2264, 64))
        if (not all(math.isfinite(v) and abs(v) < 1e7 for v in matrix)
                or any(abs(matrix[i]) > .001 for i in (3, 7, 11)) or abs(matrix[15]-1) > .001):
            raise TransientHellhoundState("플레이어 위치 갱신을 기다리고 있습니다")
        x, z = matrix[8], matrix[10]  # Native +Z basis; translation is row4.
        length = math.hypot(x, z)
        if not .1 < length < 2:
            raise TransientHellhoundState("플레이어 방향 갱신을 기다리고 있습니다")
        destination = (matrix[12]+3*x/length, matrix[13]+.35, matrix[14]+3*z/length)
        if not all(math.isfinite(v) and abs(v) < 1e7 for v in destination):
            raise TransientHellhoundState("회수 위치가 유효하지 않습니다")
        return destination

    def read_stats(self):
        with self.lock:
            if self.allocation is None:
                return dict(gate_total=0, gate_extended=0, gate_default=0,
                            teleport_total=0, teleport_success=0, teleport_fallback=0)
            raw = self.api.read(self.allocation+CODE_SIZE+HEADER_SIZE, STATS_SIZE)
            result = dict(zip(("gate_total", "gate_extended", "gate_default", "teleport_total",
                               "teleport_success", "teleport_fallback", "last_class", "wrapper", "job"),
                              struct.unpack_from("<9Q", raw)))
            result["mass_before"], result["mass_after"] = struct.unpack_from("<2f", raw, 72)
            result["destination"] = struct.unpack_from("<3f", raw, 80)
            result["character_post"] = struct.unpack_from("<3f", raw, 96)
            result["last_target"], result["qpc"], result["sequence"] = struct.unpack_from("<3Q", raw, 112)
            return result
