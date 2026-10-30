"""Leased local ATV speed/gearing/drive, tire grip and base aerodynamic drag."""
import hashlib
from contextlib import ExitStack
from pathlib import Path
import struct
import threading

import game_memory as probe
from native_game import ALLOCATION_SIZE, NativeAPI, rel_call
from ninja_mode import (NinjaMode, TransientNinjaState, WORLD_RVA, LOCAL_RVA,
                        ENTITY_RVA, QPC_IAT_RVA, VEHICLE_VTABLE_RVA, VEHICLE_INTERFACE_RVA)

SITE_RVA, PFX_VTABLE_RVA = 0x255F30, 0x197ABB8
ORIGINAL = bytes.fromhex('f30f108fdc020000')
TORQUE_SITE_RVA, TORQUE_ENTRY = 0x256808, 64
TORQUE_ORIGINAL = bytes.fromhex('e8a3f5f8ff')
WHEEL_LIMIT_SITE_RVA, WHEEL_LIMIT_ENTRY = 0x23EE54, 128
WHEEL_LIMIT_ORIGINAL = bytes.fromhex('ff9070030000')
GRIP_SITES = (0x225959,0x225B22)
GRIP_ENTRIES = (192,256)
GRIP_ORIGINALS = (bytes.fromhex('f30f598388010000'),bytes.fromhex('f30f59bb88010000'))
AERO_SITE_RVA, AERO_ENTRY = 0x2240AC, 320
AERO_ORIGINAL = bytes.fromhex('f30f104908')
ADAPTER_ENTRY = 3584
NATIVE_PREFIX_RVA, NATIVE_CONTINUATION_RVA = 0x1F2160, 0x1F220E
ORIGINALS = (ORIGINAL,TORQUE_ORIGINAL,WHEEL_LIMIT_ORIGINAL)+GRIP_ORIGINALS+(AERO_ORIGINAL,)
ENTRIES = (0,TORQUE_ENTRY,WHEEL_LIMIT_ENTRY)+GRIP_ENTRIES+(AERO_ENTRY,)
CODE_SIZE, HEADER_SIZE, LEASE_SECONDS = 4096, 576, .30
MAGIC = b'COTW_MAD_SPEED2'.ljust(16, b'\0')
STUB_SHA256 = 'a47b76af0bf08810fbe3ca0bca3013437d55ce1fa9185849509eb13d0bcf48b1'
SIGNATURES = {
    0x255F26: bytes.fromhex('0f2fd70f59cb440f55c9'),
    0x255F38: bytes.fromhex('410f28c1f30f59057c737201f30f11442478'),
    0x255F8D: bytes.fromhex('f30f118fe0020000f30f590de3727201f30f118fbc040000'),
    0x2548D0: bytes.fromhex('48895c2408574883ec20488bda488bf9e8bb0b0000488bd3488bcf488b5c24304883c4205fe9d6140000'),
    0x25693B: bytes.fromhex('0f2fbfac040000f30f1045a4f30f104da0f30f1187e81e0000'),
    0x25695C: bytes.fromhex('772a488b87b01f0000488d88b00000004805'),
    0x256954: bytes.fromhex('f30f118fe41e0000'),  # Legacy output-store hook must be restored first.
    0x256801: bytes.fromhex('488b8fd81e0000'),
    0x25680D: bytes.fromhex('488b8fd81e0000'),
    0x1E5DB0: bytes.fromhex('4c8d8180000000e9a4c30000'),
    0x23EE4E: bytes.fromhex('488b03488bcb'),
    0x23ee5a: bytes.fromhex('450f2fc80f28f0410f28c97304410f57ca0f2fce766e418bf64439b3d01200007e62498bfe'),
    0x237d10: bytes.fromhex('40534883ec2080b9ec1e000000488bd9440fbe89ed1e0000488b89d81e0000410f95c00fb69184000000e8e1abfbff488b83d01e0000f30f104848f30f584824f30f5ec80f57c00f2fc873070f570d5db46f010f28c14883c4205bc3'),
    0x225401: bytes.fromhex('817b20ffffff7f75188b8368010000898350010000c6839c01000001e9d70b0000'),
    0x22590c: bytes.fromhex('4885ff7415410f28dd410f28d30f28cf488bcfe8bc1e0100eb33'),
    0x225961: bytes.fromhex('0f57e4488b442438f30f106c24300f57dbf30f59ab900100000f28f7f30f5e7424'),
    0x2259e2: bytes.fromhex('410f2fe07606f30f5de5eb04f30f5fe5'),
    0x225ac9: bytes.fromhex('4885ff741d410f28dd410f28d30f28cf488bcfe8ff170100'),
    0x225b13: bytes.fromhex('f3440f597424300f57db488b7c2438'),
    0x225b2a: bytes.fromhex('450f57edf30f59bb90010000f3410f59fe'),
    0x225cf8: bytes.fromhex('410f2ff07606f30f5df7eb04f30f5ff7'),
    0x2240a4: bytes.fromhex('f30f5c93bc040000'),
    0x2240b1: bytes.fromhex('f30f591d0ff97001f30f10410cf30f5e15d27a3802f30f5cc1f30f5fd7f30f5d153ae67001f30f59d0f30f58d1f30f59d3f30f59d9f3410f59d4f3410f59dc'),
    NATIVE_PREFIX_RVA: bytes.fromhex('40535556574881ecb8000000488b4210498bd80f29bc2480000000488bf2440f295c2440488bf980b8e01e00000075054032edeb164180786400750c8b41584189406841c640660140b5014180786600f3440f101d071074014188686474080f57ff0f57c0eb47488b42104084ed740bf30f10415c410f57c3eb0e490fbe5065488b4960f30f10049141807804000f57ff740af30f104f3c0f2fcf7705f30f104f54f30f59c1f30f5980e41e0000'),
    NATIVE_CONTINUATION_RVA: bytes.fromhex('488bd6f3410f114020488bcfe8a10300000f28d0f30f1153184084ed740bf30f104f5c410f57cbeb0e480fbe4b65488b4760f30f100c88807b0400740af30f10473c0f2fc77705f30f104754f30f59c833edc78424e0000000000000008bd5f30f59ca0f57d2f30f10d1f30f108c24e0000000f30f5fcaf30f114b1c396f787e318bcd0f1f40006666660f1f840000000000488b4770488d4904ffc2f30f104401fcf30f594320f30f11440b203b57787ce04c8bc3488bd6488bcfe882090000'),
}


class TransientMadMaxState(TransientNinjaState):
    """Keep the user's selection while waiting for a current local ATV driver."""


class MadMaxSpeedMode:
    def __init__(self, game, writer, *, api=None, code=None):
        self.game, self.writer = game, writer
        self.api = api if api is not None else NativeAPI(game, writer)
        self.code = code if code is not None else Path(__file__).with_suffix('.bin').read_bytes()
        if len(self.code) != CODE_SIZE or hashlib.sha256(self.code).hexdigest() != STUB_SHA256:
            raise ValueError('Mad Max speed binary mismatch')
        self._local = NinjaMode(game, writer, api=self.api)
        self.allocation, self.sequence = None, 0
        self.lock = threading.RLock()

    @property
    def site(self):
        return self.game.base + SITE_RVA

    @property
    def sites(self):
        return tuple(self.game.base+rva for rva in (SITE_RVA,TORQUE_SITE_RVA,WHEEL_LIMIT_SITE_RVA)+GRIP_SITES+(AERO_SITE_RVA,))

    def _patches(self, allocation):
        return tuple(rel_call(site,allocation+entry)+b'\x90'*(len(original)-5)
                     for site,entry,original in zip(self.sites,ENTRIES,ORIGINALS))

    def _patched(self, allocation):
        return self._patches(allocation)[0]

    def _header(self):
        raw = bytearray(HEADER_SIZE)
        raw[:16] = MAGIC
        struct.pack_into('<II5Q', raw, 16, 1, CODE_SIZE, self.game.base,
                         self.game.base+QPC_IAT_RVA, self.site,
                         self.game.base+WORLD_RVA, self.game.base+LOCAL_RVA)
        struct.pack_into('<2Q', raw, 176, self.game.base+PFX_VTABLE_RVA, self.game.base+ENTITY_RVA)
        raw[192:224] = hashlib.sha256(self.code).digest()
        raw[224:256] = bytes.fromhex(probe.EXPECTED_SHA256)
        struct.pack_into('<Q',raw,312,self.sites[1])
        struct.pack_into('<2Q',raw,360,self.game.base+0x1E5DB0,self.game.base+NATIVE_CONTINUATION_RVA)
        return bytes(raw)

    def _verify_owned(self, allocation):
        if not 0x10000 <= allocation <= 0x7FFFFFFFFFFF-ALLOCATION_SIZE or allocation & 0xFFFF:
            raise RuntimeError('Invalid Mad Max allocation')
        actual, expected = self.api.read(allocation+CODE_SIZE, HEADER_SIZE), self._header()
        if (actual[:64] != expected[:64] or actual[172:256] != expected[172:256]
                or actual[312:320] != expected[312:320] or actual[360:384] != expected[360:384]
                or actual[496:512] != expected[496:512] or actual[544:] != expected[544:]
                or self.api.read(allocation,CODE_SIZE) != self.code):
            raise RuntimeError('Mad Max speed ownership mismatch')
        self.sequence = struct.unpack_from('<Q',actual,64)[0]

    def _check(self):
        for rva, expected in SIGNATURES.items():
            if self.api.read(self.game.base+rva,len(expected)) != expected:
                raise RuntimeError('Mad Max native speed calculation differs')
        owners=[]
        for site,original,entry in zip(self.sites,ORIGINALS,ENTRIES):
            raw=self.api.read(site,len(original))
            if raw==original:owners.append(None)
            elif raw[:1]==b'\xe8' and raw[5:]==b'\x90'*(len(original)-5):
                allocation=site+5+struct.unpack('<i',raw[1:5])[0]-entry
                self._verify_owned(allocation);owners.append(allocation)
            else:raise RuntimeError('Foreign ATV speed patch')
        if any(owner!=owners[0] for owner in owners[1:]):raise RuntimeError('Partial Mad Max patch')
        return owners[0]

    def _change(self, before, after):
        with ExitStack() as stack:
            for site,original in zip(self.sites,ORIGINALS):stack.enter_context(self.api.frozen_threads(site,len(original)))
            self._check()
            if any(self.api.read(site,len(raw))!=raw for site,raw in zip(self.sites,before)):
                raise RuntimeError('ATV speed instruction changed during transaction')
            protections={}
            try:
                for site,raw in zip(self.sites,after):
                    protections[site]=self.api.protect(site,len(raw),0x40)
                    self.api.write(site,raw)
                    if self.api.read(site,len(raw))!=raw:raise OSError('ATV speed postimage mismatch')
                    self.api.flush(site,len(raw));self.api.protect(site,len(raw),protections[site])
            except Exception as error:
                try:
                    for site,raw in zip(self.sites,before):
                        old=self.api.protect(site,len(raw),0x40);self.api.write(site,raw)
                        if self.api.read(site,len(raw))!=raw:raise OSError('ATV speed rollback mismatch')
                        self.api.flush(site,len(raw));self.api.protect(site,len(raw),protections.get(site,old))
                except Exception as rollback_error:
                    raise RuntimeError('ATV speed rollback failed; stop the game') from rollback_error
                raise RuntimeError('ATV speed transaction failed; previous instruction restored') from error

    def install(self):
        with self.lock:
            owned = self._check()
            if hashlib.sha256(self.game.exe.read_bytes()).hexdigest() != probe.EXPECTED_SHA256:
                raise RuntimeError('Unsupported game executable')
            if owned is not None:
                self.allocation = owned
                self.disable()
                return
            if self.allocation is None:
                self.allocation = self.api.allocate_near(self.site)
                self.api.write(self.allocation,self.code)
                self.api.write(self.allocation+CODE_SIZE,self._header())
                self._verify_owned(self.allocation)
                self.api.protect(self.allocation,CODE_SIZE,0x20)
                self.api.flush(self.allocation,CODE_SIZE)
            else:
                self._verify_owned(self.allocation)
            self.disable()
            self._change(ORIGINALS,self._patches(self.allocation))

    def _binding(self):
        binding = self._local._binding()
        vehicle = self._local._vehicle_binding(binding)
        if vehicle is None:
            raise TransientMadMaxState('Mad Max is waiting for the local ATV driver')
        pfx = struct.unpack('<Q',self.api.read(vehicle['vehicle']+0x4A98,8))[0]
        if not pfx or self.api.read(pfx,8) != struct.pack('<Q',self.game.base+PFX_VTABLE_RVA):
            raise TransientMadMaxState('Current ATV physics is changing')
        speed_bits = self.api.read(pfx+0x2DC,4)
        speed = struct.unpack('<f',speed_bits)[0]
        if not 1. <= speed <= 300.:
            raise RuntimeError('ATV base speed is outside the supported range')
        transmission = struct.unpack('<Q',self.api.read(pfx+0x1ED8,8))[0]
        if not 0x10000 <= transmission <= 0x7FFFFFFFFFFF-0xF0:
            raise TransientMadMaxState('Current ATV physics is changing')
        if (self._local._vehicle_binding(binding) != vehicle
                or self.api.read(vehicle['vehicle']+0x4A98,8) != struct.pack('<Q',pfx)
                or self.api.read(pfx+0x2DC,4) != speed_bits
                or self.api.read(pfx+0x1ED8,8) != struct.pack('<Q',transmission)):
            raise TransientMadMaxState('Current ATV changed during speed binding')
        return dict(binding, vehicle=vehicle['vehicle'], vehicle_source=vehicle['source'],
                    vehicle_handle=vehicle['handle'], vehicle_type=vehicle['vehicle_type'],
                    pfx=pfx, speed_bits=speed_bits,transmission=transmission)

    def _lease(self, deadline, binding=None):
        header = self.allocation+CODE_SIZE
        self.sequence = ((self.sequence+2)&0xFFFFFFFFFFFFFFFE) or 2
        self.api.write(header+64,struct.pack('<Q',self.sequence-1))
        try:
            if binding:
                names = ('character','player','handle','pool','mapping','source','vehicle',
                         'vehicle_source','vehicle_handle','vehicle_type','pfx')
                self.api.write(header+80,struct.pack('<11Q',*(binding[name] for name in names))+binding['speed_bits'])
                self.api.write(header+384,struct.pack('<Q',binding['transmission']))
            self.api.write(header+72,struct.pack('<Q',deadline))
            self.api.write(header+64,struct.pack('<Q',self.sequence))
        except Exception:
            self.api.write(header+72,bytes(8))
            raise

    def publish(self):
        with self.lock:
            try:
                binding = self._binding()
                if self.allocation is None:
                    self.install()
                    binding = self._binding()
                if self._check() != self.allocation:
                    raise RuntimeError('Mad Max speed hook is not installed')
                now, frequency = self.api.clock()
                self._lease(now+int(LEASE_SECONDS*frequency),binding)
                return 1
            except Exception as error:
                self.disable()
                if isinstance(error,TransientNinjaState) and not isinstance(error,TransientMadMaxState):
                    raise TransientMadMaxState(str(error)) from error
                raise

    def disable(self):
        with self.lock:
            if self.allocation is not None:
                try:
                    self._lease(0)
                except OSError:
                    if self.api.is_running():raise

    def close(self):
        with self.lock:
            try:
                self.disable()
                if self.allocation is not None and self._check() == self.allocation:
                    self._change(self._patches(self.allocation),ORIGINALS)
            except OSError:
                if self.api.is_running():raise
            # In-flight stubs return after the complete original instruction; retain code.

    def read_stats(self):
        with self.lock:
            if self.allocation is None:return {}
            raw = self.api.read(self.allocation+CODE_SIZE+256,288)
            calls,scaled,fallback = struct.unpack_from('<3Q',raw)
            original,limit = struct.unpack_from('<2f',raw,24)
            pfx,qpc = struct.unpack_from('<2Q',raw,32)
            reason = struct.unpack_from('<I',raw,48)[0]
            torque_calls,torque_scaled=struct.unpack_from('<2Q',raw,64)
            original_torque,torque_output=struct.unpack_from('<2f',raw,80)
            torque_fallback=struct.unpack_from('<Q',raw,96)[0]
            original_final_drive,effective_final_drive,wheel_torque=struct.unpack_from('<3f',raw,136)
            wheel_limit_calls,wheel_limit_scaled,wheel_limit_fallback=struct.unpack_from('<3Q',raw,160)
            original_wheel_rpm,effective_wheel_rpm=struct.unpack_from('<2f',raw,184)
            grip_calls,grip_scaled,grip_fallback=struct.unpack_from('<3Q',raw,192)
            original_grip_limit,effective_grip_limit,grip_axis=struct.unpack_from('<2fI',raw,216)
            grip_wheel=struct.unpack_from('<Q',raw,232)[0]
            aero_calls,aero_scaled,aero_fallback=struct.unpack_from('<3Q',raw,256)
            original_aero_coefficient,effective_aero_coefficient=struct.unpack_from('<2f',raw,280)
            return dict(calls=calls,scaled=scaled,fallback=fallback,original_kph=original,
                        limit_kph=limit,pfx=pfx,qpc=qpc,reason=reason,torque_calls=torque_calls,
                        torque_scaled=torque_scaled,torque_fallback=torque_fallback,
                        original_torque=original_torque,torque_output=torque_output,
                        original_final_drive=original_final_drive,effective_final_drive=effective_final_drive,
                        wheel_torque=wheel_torque,wheel_limit_calls=wheel_limit_calls,
                        wheel_limit_scaled=wheel_limit_scaled,wheel_limit_fallback=wheel_limit_fallback,
                        original_wheel_rpm=original_wheel_rpm,effective_wheel_rpm=effective_wheel_rpm,
                        grip_calls=grip_calls,grip_scaled=grip_scaled,grip_fallback=grip_fallback,
                        original_grip_limit=original_grip_limit,effective_grip_limit=effective_grip_limit,
                        grip_axis=grip_axis,grip_wheel=grip_wheel,
                        aero_calls=aero_calls,aero_scaled=aero_scaled,aero_fallback=aero_fallback,
                        original_aero_coefficient=original_aero_coefficient,
                        effective_aero_coefficient=effective_aero_coefficient)
