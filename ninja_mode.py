"""Leased local-player AI movement-hearing, vision and scent filters."""
import hashlib
from pathlib import Path
import struct
import threading

import game_memory as probe
from native_game import ALLOCATION_SIZE, NativeAPI, rel_call

CALL_RVA, ORIGINAL_RVA = 0x5EC96C, 0x5F0D00
ORIGINAL_CALL = bytes.fromhex("e88f430000")
VISION_CALL_RVA, VISION_ORIGINAL_RVA = 0x612F3E, 0x5ED230
VISION_ORIGINAL_CALL = bytes.fromhex("e8eda2fdff")
SCENT_CALL_RVA, SCENT_ORIGINAL_RVA = 0x612C7B, 0x5ECD40
SCENT_ORIGINAL_CALL = bytes.fromhex("e8c0a0fdff")
WORLD_RVA, LOCAL_RVA, ENTITY_RVA = 0x27C5DC8, 0x27F1478, 0x27C5D50
QPC_IAT_RVA = 0x1920518
CHAR_VTABLE_RVA, PLAYER_VTABLE_RVA = 0x1A60028, 0x1EE24A0
CODE_SIZE, HEADER_SIZE, STATS_SIZE = 4096, 256, 64
BUNDLE_SIZE = CODE_SIZE * 3
VISION_STATS_OFFSET = 288
MAGIC = b"COTW_NINJA_V1".ljust(16, b"\0")
VISION_MAGIC = b"COTW_NINJAVIS_V1".ljust(16, b"\0")
SCENT_MAGIC = b"COTW_NINJASNT_V1".ljust(16, b"\0")
VEHICLE_VTABLE_RVA, VEHICLE_INTERFACE_RVA = 0x1F59DA0, 0x1F5A248
LEASE_SECONDS = .30
STUB_SHA256 = "5199ef0766aed7094b0bc5fe8c1713f2431ec8ccd23404f73ac43cc49104317e"
VISION_STUB_SHA256 = "79b4862d5eb3a30ec06bbcc578770185e26331e6bde93480bf9ef70cc7cd6831"
SCENT_STUB_SHA256 = "5b7a2fdc8113b00d469486174436ddbd5d1dcdca9017d0569f7d40ce0597bab9"
SIGNATURES = {
    ORIGINAL_RVA: bytes.fromhex("4881ec880000000f297424700f57f60fb6c2440f29442450450f57c0"),
    0x5EC971: bytes.fromhex("f30f5ff7440f28f00f28bc24b0000000f3410f59f1440f288c2490000000f3440f58f6"),
    0x5EC6F3: bytes.fromhex("4585c07455f6862401000002744c498b96c8030000"),
    VISION_ORIGINAL_RVA: bytes.fromhex("4c8bdc49895b208954241057415641574881ec00010000488bf9440fb6d248b9b301000000010000450f295b8848b825232284e49cf2cb4d8bf84c33"),
    0x612F43: bytes.fromhex("f783d8000000000001007406410f28f0eb04410f28f1f30f59f00f2ff77667488bd3488b5c2430"),
    SCENT_ORIGINAL_RVA: bytes.fromhex("488bc44889582041564881ecb00000000f2970e849bab301000000010000440f"),
    0x612C57: bytes.fromhex("48895c24304c897c2428488d44246048894424200f28d8410f28d58b9580000000498bcd"),
    0x612C80: bytes.fromhex("f783d8000000000001007406410f28f1eb04410f28f0f30f59f00f2f"),
}


class TransientNinjaState(RuntimeError):
    """An identity transition: expire leases and retry only a fresh binding."""


class NinjaMode:
    def __init__(self, game, writer, *, api=None, code=None):
        self.game, self.writer = game, writer
        self.api = api if api is not None else NativeAPI(game, writer)
        bundle = code if code is not None else Path(__file__).with_name("ninja_stub.bin").read_bytes()
        self.code, self.vision_code, self.scent_code = (bundle[:CODE_SIZE], bundle[CODE_SIZE:CODE_SIZE*2],
                                                     bundle[CODE_SIZE*2:])
        if (len(bundle) != BUNDLE_SIZE or hashlib.sha256(self.code).hexdigest() != STUB_SHA256
                or hashlib.sha256(self.vision_code).hexdigest() != VISION_STUB_SHA256
                or hashlib.sha256(self.scent_code).hexdigest() != SCENT_STUB_SHA256):
            raise ValueError("닌자 모드 바이너리를 확인하지 못했습니다")
        self.allocation = None
        self.sequence = 0
        self.vision_allocation = None
        self.vision_sequence = 0
        self.scent_allocation = None
        self.scent_sequence = 0
        self.last_binding = None
        self.last_vehicle_binding = None
        self.lock = threading.RLock()

    @property
    def site(self):
        return self.game.base + CALL_RVA

    @property
    def vision_site(self):
        return self.game.base + VISION_CALL_RVA

    @property
    def scent_site(self):
        return self.game.base + SCENT_CALL_RVA

    def _u32(self, address):
        return struct.unpack("<I", self.api.read(address, 4))[0]

    def _qword(self, address):
        return struct.unpack("<Q", self.api.read(address, 8))[0]

    def _check_signatures(self):
        for rva, expected in SIGNATURES.items():
            if self.api.read(self.game.base+rva, len(expected)) != expected:
                raise RuntimeError("닌자 모드 감지 코드가 검증된 버전과 다릅니다")
        for vision, scent, site, original in ((False, False, self.site, ORIGINAL_CALL),
                                             (True, False, self.vision_site, VISION_ORIGINAL_CALL),
                                             (False, True, self.scent_site, SCENT_ORIGINAL_CALL)):
            current = self.api.read(site, 5)
            if current == original:
                continue
            if current[:1] != b"\xe8":
                raise RuntimeError("닌자 모드 호출 코드가 다른 프로그램에 의해 변경되었습니다")
            self._verify_owned(site+5+struct.unpack("<i", current[1:])[0], vision, scent)

    def _header(self, vision=False, scent=False):
        result = bytearray(HEADER_SIZE)
        result[:16] = SCENT_MAGIC if scent else VISION_MAGIC if vision else MAGIC
        struct.pack_into("<II5Q", result, 16, 1, 0, self.game.base,
                         self.game.base+QPC_IAT_RVA, self.game.base+(SCENT_ORIGINAL_RVA if scent else VISION_ORIGINAL_RVA if vision else ORIGINAL_RVA),
                         self.game.base+LOCAL_RVA, self.game.base+ENTITY_RVA)
        result[128:160] = hashlib.sha256(self.scent_code if scent else self.vision_code if vision else self.code).digest()
        result[160:192] = bytes.fromhex(probe.EXPECTED_SHA256)
        struct.pack_into("<5Q", result, 192, ALLOCATION_SIZE, self.scent_site if scent else self.vision_site if vision else self.site,
                         self.game.base+CHAR_VTABLE_RVA, self.game.base+PLAYER_VTABLE_RVA,
                         self.game.base+WORLD_RVA)
        if vision:
            struct.pack_into("<2Q", result, 232, self.game.base+VEHICLE_VTABLE_RVA,
                             self.game.base+VEHICLE_INTERFACE_RVA)
        return bytes(result)

    def _verify_owned(self, allocation, vision=False, scent=False):
        if not 0x10000 <= allocation <= 0x7FFFFFFFFFFF-ALLOCATION_SIZE or allocation & 0xFFFF:
            raise RuntimeError("기존 닌자 모드 위치가 유효하지 않습니다")
        actual = self.api.read(allocation+CODE_SIZE, HEADER_SIZE)
        expected = self._header(vision, scent)
        if (actual[:64] != expected[:64] or actual[128:] != expected[128:]
                or self.api.read(allocation, CODE_SIZE) != (self.scent_code if scent else self.vision_code if vision else self.code)):
            raise RuntimeError("기존 닌자 모드 소유권과 코드를 확인하지 못했습니다")
        setattr(self, "scent_sequence" if scent else "vision_sequence" if vision else "sequence", struct.unpack_from("<Q", actual, 64)[0])

    def _install(self, vision=False, scent=False):
        self._check_signatures()
        if hashlib.sha256(self.game.exe.read_bytes()).hexdigest() != probe.EXPECTED_SHA256:
            raise RuntimeError("지원하지 않는 게임 파일이어서 닌자 모드를 시작하지 않았습니다")
        site = self.scent_site if scent else self.vision_site if vision else self.site
        original = SCENT_ORIGINAL_CALL if scent else VISION_ORIGINAL_CALL if vision else ORIGINAL_CALL
        code = self.scent_code if scent else self.vision_code if vision else self.code
        attr = "scent_allocation" if scent else "vision_allocation" if vision else "allocation"
        current = self.api.read(site, 5)
        if current != original:
            if current[:1] != b"\xe8":
                raise RuntimeError("닌자 모드 호출 코드가 다른 프로그램에 의해 변경되었습니다")
            target = site+5+struct.unpack("<i", current[1:])[0]
            self._verify_owned(target, vision, scent)
            setattr(self, attr, target)
            self._publish(None, 0, vision=vision, scent=scent)
            return
        allocation = self.api.allocate_near(site)
        self.api.write(allocation, code)
        self.api.write(allocation+CODE_SIZE, self._header(vision, scent)+bytes(96 if vision else STATS_SIZE))
        self._verify_owned(allocation, vision, scent)
        self.api.protect(allocation, CODE_SIZE, 0x20)
        self.api.flush(allocation, CODE_SIZE)
        patch = rel_call(site, allocation)
        with self.api.frozen_threads(site, 5):
            self._check_signatures()
            if self.api.read(site, 5) != original:
                raise RuntimeError("설치 중 닌자 모드 호출 코드가 바뀌었습니다")
            old = self.api.protect(site, 5, 0x40)
            try:
                self.api.write(site, patch)
                if self.api.read(site, 5) != patch:
                    raise OSError("닌자 모드 호출 코드 기록 검증 실패")
                self.api.flush(site, 5)
                self.api.protect(site, 5, old)
            except Exception as error:
                try:
                    self.api.protect(site, 5, 0x40)
                    self.api.write(site, original)
                    if self.api.read(site, 5) != original:
                        raise OSError("원본 호출 코드 복원 검증 실패")
                    self.api.flush(site, 5)
                    self.api.protect(site, 5, old)
                except Exception as rollback_error:
                    raise RuntimeError("닌자 모드 설치와 원본 복원에 실패했습니다. 게임을 종료하세요") from rollback_error
                raise RuntimeError("닌자 모드 설치 실패: 원본 호출 코드를 복원했습니다") from error
        setattr(self, attr, allocation)

    def _binding(self):
        world = self._qword(self.game.base+WORLD_RVA)
        if not world or self._u32(world+0x48) != 7 or self.api.read(world+0x7C, 1) == b"\0":
            raise RuntimeError("사냥터에 들어간 뒤 닌자 모드를 켜세요")
        local_manager = self._qword(self.game.base+LOCAL_RVA)
        if not local_manager:
            raise TransientNinjaState("현재 플레이어 연결이 변경 중입니다")
        local_slot = self._qword(local_manager+0x60)
        if not local_slot:
            raise TransientNinjaState("현재 플레이어 연결이 변경 중입니다")
        character = self._qword(local_slot+0x170)
        if not character or self._qword(character) != self.game.base+CHAR_VTABLE_RVA:
            raise TransientNinjaState("현재 플레이어 캐릭터가 변경 중입니다")
        player_link = self._qword(character+0x2400)
        if player_link < 0x10010:
            raise TransientNinjaState("현재 플레이어 연결이 변경 중입니다")
        player = player_link-0x10
        if self._qword(player) != self.game.base+PLAYER_VTABLE_RVA or self._qword(player+0x68) != character:
            raise TransientNinjaState("현재 로컬 플레이어 연결이 변경 중입니다")
        entity_manager = self._qword(self.game.base+ENTITY_RVA)
        if not entity_manager:
            raise RuntimeError("게임 AI 입력 관리자를 확인하지 못했습니다")
        pool = self._qword(entity_manager+0x20290)
        if not pool:
            raise RuntimeError("게임 AI 입력 목록을 확인하지 못했습니다")
        handle = self._u32(character+0x2098)
        index = handle >> 16
        capacity = self._u32(pool+0x120)
        mapping = self._qword(pool+8)
        if not 0 < capacity <= 65536 or not mapping:
            raise RuntimeError("게임 AI 입력 목록이 유효하지 않습니다")
        if not handle & 0xFFFF or index >= capacity:
            raise TransientNinjaState("플레이어 감지 핸들이 변경 중입니다")
        entry = self._u32(mapping+index*4)
        if entry & 0xFFFF != handle & 0xFFFF:
            raise TransientNinjaState("플레이어 감지 핸들 연결이 변경 중입니다")
        source = self._qword(pool)+(entry >> 16)*0x180
        record = self.api.read(source, 0x180)
        if (struct.unpack_from("<I", record, 0x170)[0] != 1 or not record[0x17C] & 1
                or struct.unpack_from("<Q", record, 0xB8)[0] != character
                or struct.unpack_from("<H", record, 0x174)[0] != index):
            raise TransientNinjaState("현재 플레이어의 AI 입력이 변경 중입니다")
        # A fresh closed binding is required on each publish. Never select a
        # character by proximity, vtable alone, or a fixed pool slot number.
        if (self._qword(local_slot+0x170) != character or self._qword(player+0x68) != character
                or self._u32(character+0x2098) != handle or self._u32(mapping+index*4) != entry
                or self._qword(pool+8) != mapping or self._qword(entity_manager+0x20290) != pool):
            raise TransientNinjaState("플레이어 AI 입력 연결이 변경 중입니다")
        return dict(character=character, source=source, handle=handle, pool=pool, player=player, mapping=mapping)

    def _vehicle_binding(self, binding):
        """Resolve only the local driver's current typed vehicle source."""
        pool, mapping, handle = binding["pool"], binding["mapping"], binding["handle"]
        indices = self._qword(pool+0x50)
        count = struct.unpack("<H", self.api.read(pool+0x58, 2))[0]
        if count > 4096 or (count and not indices):
            raise RuntimeError("현재 차량 AI 입력 목록을 확인하지 못했습니다")
        nodes, capacity = self._qword(pool), self._u32(pool+0x120)
        slots = self.api.read(indices, count*2) if count else b""
        matches = []
        for slot in struct.unpack("<"+"H"*count, slots) if count else ():
            source = nodes+slot*0x180
            record = self.api.read(source, 0x180)
            if (struct.unpack_from("<I", record, 0x170)[0] != 2 or not record[0x17C] & 1
                    or struct.unpack_from("<I", record, 0x54)[0] != handle):
                continue
            interface = struct.unpack_from("<Q", record, 0x40)[0]
            if interface < 0x10008:
                raise TransientNinjaState("현재 탑승 차량 연결이 변경 중입니다")
            vehicle = interface-8
            if (self._qword(vehicle) != self.game.base+VEHICLE_VTABLE_RVA
                    or self._qword(interface) != self.game.base+VEHICLE_INTERFACE_RVA):
                raise RuntimeError("현재 탑승 차량 형식을 확인하지 못했습니다")
            vehicle_handle = self._u32(vehicle+0x4A28)
            index = vehicle_handle >> 16
            if not vehicle_handle & 0xFFFF or index >= capacity:
                raise TransientNinjaState("현재 차량 감지 핸들이 변경 중입니다")
            entry = self._u32(mapping+index*4)
            vehicle_type = self._u32(vehicle+0x5020)
            if (entry & 0xFFFF != vehicle_handle & 0xFFFF or nodes+(entry >> 16)*0x180 != source
                    or struct.unpack_from("<H", record, 0x174)[0] != index
                    or self._u32(binding["source"]+0x120) != vehicle_type):
                raise TransientNinjaState("현재 차량 AI 입력 연결이 변경 중입니다")
            # A driver can enter/leave between any two reads. Never publish a
            # candidate whose closed binding changed during this snapshot.
            if (self._qword(source+0x40) != interface or self._u32(source+0x54) != handle
                    or self._u32(source+0x170) != 2 or not self.api.read(source+0x17C, 1)[0] & 1
                    or struct.unpack("<H", self.api.read(source+0x174, 2))[0] != index
                    or self._u32(vehicle+0x4A28) != vehicle_handle
                    or self._u32(vehicle+0x5020) != vehicle_type
                    or self._u32(mapping+index*4) != entry):
                raise TransientNinjaState("차량 승하차 연결이 변경 중입니다")
            matches.append(dict(vehicle=vehicle, source=source, handle=vehicle_handle, vehicle_type=vehicle_type))
        if len(matches) > 1:
            raise TransientNinjaState("현재 탑승 차량 연결이 변경 중입니다")
        if (self._qword(pool+0x50) != indices or struct.unpack("<H", self.api.read(pool+0x58, 2))[0] != count
                or self._qword(pool) != nodes or self._qword(pool+8) != mapping
                or self._u32(pool+0x120) != capacity
                or (count and self.api.read(indices, count*2) != slots)):
            raise TransientNinjaState("차량 AI 입력 목록이 변경 중입니다")
        if self._binding() != binding:
            raise TransientNinjaState("차량 확인 중 플레이어 연결이 변경 중입니다")
        # source+120 is a vehicle definition ID and +124 contains audio flags.
        # These hints are not an atomic current-driver binding in transitions.
        # Without a closed-bound local-driver vehicle, publish only the player.
        return matches[0] if matches else None

    def _publish(self, binding, deadline, *, vision=False, scent=False, vehicle=None):
        allocation = self.scent_allocation if scent else self.vision_allocation if vision else self.allocation
        header = allocation+CODE_SIZE
        sequence_attr = "scent_sequence" if scent else "vision_sequence" if vision else "sequence"
        sequence = ((getattr(self, sequence_attr)+2) & 0xFFFFFFFFFFFFFFFE) or 2
        setattr(self, sequence_attr, sequence)
        self.api.write(header+64, struct.pack("<Q", sequence-1))
        try:
            values = [deadline] + ([binding[k] for k in ("character", "source", "handle", "pool", "player", "mapping")] if binding else [0]*6)
            self.api.write(header+72, struct.pack("<7Q", *values))
            if vision:
                self.api.write(header+256, struct.pack("<4Q", *([vehicle[k] for k in
                               ("vehicle", "source", "handle", "vehicle_type")] if vehicle else [0]*4)))
            self.api.write(header+64, struct.pack("<Q", sequence))
        except Exception:
            try:
                self.api.write(header+72, bytes(8))
            except Exception:
                pass
            raise

    def publish(self):
        with self.lock:
            try:
                self._check_signatures()
                binding = self._binding()
                vehicle = self._vehicle_binding(binding)
                if self.allocation is None:
                    self._install()
                if self.vision_allocation is None:
                    self._install(vision=True)
                if self.scent_allocation is None:
                    self._install(scent=True)
                binding = self._binding()  # every install may pause the game
                vehicle = self._vehicle_binding(binding)
                for site, allocation in ((self.site, self.allocation), (self.vision_site, self.vision_allocation),
                                         (self.scent_site, self.scent_allocation)):
                    if self.api.read(site, 5) != rel_call(site, allocation):
                        raise RuntimeError("닌자 모드 호출 코드가 바뀌었습니다")
                now, frequency = self.api.clock()
                deadline = now+int(LEASE_SECONDS*frequency)
                self._publish(binding, deadline)
                self._publish(binding, deadline, vision=True, vehicle=vehicle)
                self._publish(binding, deadline, scent=True)
                self.last_binding = binding
                self.last_vehicle_binding = vehicle
                return 1
            except Exception as error:
                try:
                    self.disable()
                except OSError:
                    # A failed lease write is fatal even when the original
                    # cause was a recoverable identity transition.
                    if isinstance(error, TransientNinjaState):
                        raise
                raise

    def disable(self):
        with self.lock:
            errors = []
            for vision, scent, attr in ((False, False, "allocation"), (True, False, "vision_allocation"),
                                       (False, True, "scent_allocation")):
                if getattr(self, attr) is None:
                    continue
                try:
                    self._publish(None, 0, vision=vision, scent=scent)
                except OSError as error:
                    if self.api.is_running():
                        errors.append(error)
                    else:
                        setattr(self, attr, None)
            self.last_binding = None
            self.last_vehicle_binding = None
            if errors:
                raise errors[0]

    def close(self):
        self.disable()  # No unpatch/free while game threads may execute code.

    def read_stats(self):
        """Best-effort diagnostics only; never controls gameplay or writes."""
        with self.lock:
            if self.allocation is None:
                return dict(total=0, filtered=0, fallback=0)
            raw = self.api.read(self.allocation+CODE_SIZE+HEADER_SIZE, STATS_SIZE)
            total, filtered, fallback, sequence, event, material, vegetation, movement, source, qpc = struct.unpack("<4Q4f2Q", raw)
            result = dict(total=total, filtered=filtered, fallback=fallback, sequence=sequence,
                          event=event, material=material, vegetation=vegetation, movement=movement,
                          source=source, qpc=qpc)
            if self.vision_allocation is not None:
                raw = self.api.read(self.vision_allocation+CODE_SIZE+VISION_STATS_OFFSET, STATS_SIZE)
                total, player, vehicle, fallback, original, filtered, source, qpc, sequence = struct.unpack("<4Q2f3Q", raw)
                result["vision"] = dict(total=total, filtered=player+vehicle, player=player, vehicle=vehicle,
                                        fallback=fallback, original_score=original, returned_score=filtered,
                                        source=source, qpc=qpc, sequence=sequence)
            if self.scent_allocation is not None:
                raw = self.api.read(self.scent_allocation+CODE_SIZE+HEADER_SIZE, STATS_SIZE)
                total, filtered, _, fallback, original, returned, source, qpc, sequence = struct.unpack("<4Q2f3Q", raw)
                result["scent"] = dict(total=total, filtered=filtered, fallback=fallback,
                                       original_score=original, returned_score=returned,
                                       source=source, qpc=qpc, sequence=sequence)
            return result
