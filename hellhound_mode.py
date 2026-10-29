"""Leased local Retriever carry using the original corpse and native physics.

Native pickup always runs once; only a validated dead class2..9 can be carried.
Actual animal class, health, weight, rewards and save fields are untouched.
"""
from contextlib import ExitStack
import hashlib
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
TICK_CALL_RVA, TICK_FUNCTION_RVA = 0x68B1F8, 0x6B1540
SPEED_CALL_RVA, SPEED_FUNCTION_RVA = 0x714A0D, 0x8FB990
PAIR_SITE_RVA, PAIR_FUNCTION_RVA = 0x1FF4EA8, 0xFEFEC0
ORIGINAL_TICK_CALL, ORIGINAL_SPEED_CALL = bytes.fromhex("e843630200"), bytes.fromhex("e87e6f1e00")
FUNCTIONS = (TICK_FUNCTION_RVA, 0x3223A0, 0x3320E0, 0xFCF7A0,
             0x69DB70, 0x67A0B0, SPEED_FUNCTION_RVA, PAIR_FUNCTION_RVA,
             0x1FF4E88, 0x1984248, 0x223C008, 0xFCDA50, 0x27A8320)
JOB_VTABLE_RVA, HOST_RVA = 0x1DEF1D8, 0x27C5DB8
CODE_SIZE, PICKUP_OFFSET, HEADER_SIZE, STATS_SIZE = 24576, 4096, 512, 304
TICK_OFFSET, PAIR_OFFSET, SPEED_OFFSET = 8192, 16384, 20480
STATE_OFFSET, BODY_OFFSET, MAX_BODIES = 1024, 2048, 256
MAGIC = b"COTW_HELLHND_V3".ljust(16, b"\0")
LEASE_SECONDS = .30
STUB_SHA256 = "1ccc9b3a0a53eac8fe07228fec3723a5823ffb89600b5eb7386f9a29ceeb3322"
SIGNATURES = {
    0x5DAB92: bytes.fromhex("e8a90e3200"),  # Reject leftover V1 weight hooks; never patch this site.
    0x8F1DC5: bytes.fromhex("488b1a4885db0f841a030000488bcb"),
    0x6CB24F: bytes.fromhex("4c8d0d9af3ed014c8bc3488bd7498bcf"),
    0x6CB264: bytes.fromhex("488bcb"),
    PICKUP_FUNCTION_RVA: bytes.fromhex("40534883ec60c60101498bd8410f10014c8d442420488bcb410f1049100f11442420410f1041200f114c2430410f1049300f114424400f114c2450e8b013feff4533c0488d0d96bf3a01418d5012e88d616c00488d54247089442470488bcbe8dcadfdff4883c4605bc3"),
    CHAR_SETTER_RVA: bytes.fromhex("48895c24184889742420574881ec800000000f1002488db15c220000488bda48"),
    RAGDOLL_SETTER_RVA: bytes.fromhex("405355565741564881ecb0060000488b05c3af2d024833c448898424a0060000"),
    TICK_FUNCTION_RVA: bytes.fromhex("488bc44889581855488d68984881ec60010000"),
    PAIR_FUNCTION_RVA: bytes.fromhex("48895c2420565741574883ec20488bd94d8bf8"),
    0x3223A0: bytes.fromhex("4c8b49104c8bd94d63c0498b41484e63"),
    0x3320E0: bytes.fromhex("48895c2418574881ec900000000f29b4"),
    0xFCF7A0: bytes.fromhex("488974242089542410574883ec204863"),
    0x69DB70: bytes.fromhex("4c8bdc565741564883ec5049c743b8fe"),
    0x67A0B0: bytes.fromhex("48895c24084889742410574883ec208b"),
    0xFCDA50: bytes.fromhex("48896c2418488974242089542410574883ec30"),
    SPEED_FUNCTION_RVA: bytes.fromhex("4883ec68488b41184885c00f848a000000"),
}


class TransientHellhoundState(RuntimeError):
    """Expire the hooks and wait for a fresh local Retriever job binding."""


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
        return (gate, rel_call(self.pickup_site, allocation+PICKUP_OFFSET),
                rel_call(self.game.base+TICK_CALL_RVA, allocation+TICK_OFFSET),
                rel_call(self.game.base+SPEED_CALL_RVA, allocation+SPEED_OFFSET),
                struct.pack("<Q", allocation+PAIR_OFFSET))

    def _sites(self):
        return ((self.site, ORIGINAL_GATE), (self.pickup_site, ORIGINAL_PICKUP_CALL),
                (self.game.base+TICK_CALL_RVA, ORIGINAL_TICK_CALL),
                (self.game.base+SPEED_CALL_RVA, ORIGINAL_SPEED_CALL),
                (self.game.base+PAIR_SITE_RVA, struct.pack("<Q", self.game.base+PAIR_FUNCTION_RVA)))

    def _header(self):
        result = bytearray(HEADER_SIZE)
        result[:16] = MAGIC
        struct.pack_into("<II5Q", result, 16, 3, 0, self.game.base,
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
        struct.pack_into("<"+"Q"*len(FUNCTIONS), result, 384,
                         *(self.game.base+rva for rva in FUNCTIONS))
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
        sites = self._sites()
        current = tuple(self.api.read(site, len(original)) for site, original in sites)
        gate = current[0]
        if current == tuple(original for _, original in sites):
            return None
        if gate[:1] == b"\xe8":
            allocation = self.site+5+struct.unpack("<i", gate[1:5])[0]
            if current == self._patches(allocation):
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
        self.api.write(allocation+CODE_SIZE+STATE_OFFSET,
                       bytes(BODY_OFFSET+MAX_BODIES*32-STATE_OFFSET))
        self._verify_owned(allocation)
        self.api.protect(allocation, CODE_SIZE, 0x20)
        self.api.flush(allocation, CODE_SIZE)
        sites = tuple((site, original, patch) for (site, original), patch in zip(self._sites(), patches))
        # Nested suspension counts keep every thread paused while all sites
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
            if binding:
                self.api.write(header+352, struct.pack("<2Q", binding["frequency"], binding["frequency"]//4))
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
                now, frequency = self.api.clock()
                binding["frequency"] = frequency
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

    def read_stats(self):
        with self.lock:
            if self.allocation is None:
                return dict(gate_total=0, gate_extended=0, gate_default=0,
                            pickup_total=0, carry_registered=0, carry_fallback=0, phase=0,
                            tick_total=0, pair_total=0, head_updates=0, release_total=0)
            raw = self.api.read(self.allocation+CODE_SIZE+HEADER_SIZE, STATS_SIZE)
            result = dict(zip(("gate_total", "gate_extended", "gate_default", "pickup_total",
                               "carry_registered", "carry_fallback", "last_class", "wrapper", "job"),
                              struct.unpack_from("<9Q", raw)))
            result["mass_before"], result["mass_after"] = struct.unpack_from("<2f", raw, 72)
            result["destination"] = struct.unpack_from("<3f", raw, 80)
            result["character_post"] = struct.unpack_from("<3f", raw, 96)
            result["last_target"], result["qpc"], result["sequence"] = struct.unpack_from("<3Q", raw, 112)
            result["phase"] = self._u32(self.allocation+CODE_SIZE+STATE_OFFSET)
            result["floor_seen"] = self._u32(self.allocation+CODE_SIZE+STATE_OFFSET+124)
            result["reason"] = self._u32(self.allocation+CODE_SIZE+STATE_OFFSET+144)
            result["body_count"] = self._u32(self.allocation+CODE_SIZE+STATE_OFFSET+96)
            result["head_bone"] = self._u32(self.allocation+CODE_SIZE+STATE_OFFSET+100)
            result["cancel_detail"] = self._u32(self.allocation+CODE_SIZE+STATE_OFFSET+184)
            result["head_distance_squared"] = struct.unpack("<f", self.api.read(self.allocation+CODE_SIZE+STATE_OFFSET+188, 4))[0]
            result["anchor_jump_squared"] = struct.unpack_from("<f", raw, 200)[0]
            result["tick_delta"] = struct.unpack_from("<Q", raw, 208)[0]
            result["body_updates"] = struct.unpack_from("<Q", raw, 192)[0]
            result["binding_skips"] = struct.unpack_from("<Q", raw, 216)[0]
            for name, offset in (("head_before", 224), ("head_desired", 240), ("head_after", 256), ("jaw_anchor", 272)):
                result[name] = struct.unpack_from("<3f", raw, offset)
            result.update(zip(("tick_total", "pair_total", "head_updates", "release_total"),
                              struct.unpack_from("<4Q", raw, 160)))
            return result
