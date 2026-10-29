"""Game-free fake API and execution tests for the real assembled ninja stub."""
from contextlib import contextmanager
import hashlib
import itertools
import json
from pathlib import Path
import struct
import types
import unittest
from unittest.mock import patch

import ninja_mode as m


class FakeAPI:
    base, allocation = 0x140000000, 0x150000000
    def __init__(self):
        self.memory = {}; self.events = []; self.failure = None; self.running = True
        for rva, data in m.SIGNATURES.items():
            self.put(self.base+rva, data)
        self.put(self.base+m.CALL_RVA, m.ORIGINAL_CALL)
        self.put(self.base+m.VISION_CALL_RVA, m.VISION_ORIGINAL_CALL)
        self.put(self.base+m.SCENT_CALL_RVA, m.SCENT_ORIGINAL_CALL)

    def put(self, address, data):
        self.memory.update((address+i, byte) for i, byte in enumerate(data))

    def read(self, address, size):
        if not self.running:
            raise OSError("process exited")
        return bytes(self.memory.get(address+i, 0) for i in range(size))

    def write(self, address, data):
        self.events.append(("write", address, len(data)))
        if not self.running:
            raise OSError("process exited")
        if address == self.base+m.CALL_RVA and data != m.ORIGINAL_CALL and self.failure == "partial":
            self.failure = None; self.put(address, data[:2]); raise OSError("partial patch")
        if address == self.base+m.VISION_CALL_RVA and data != m.VISION_ORIGINAL_CALL and self.failure == "vision_partial":
            self.failure = None; self.put(address, data[:2]); raise OSError("partial visual patch")
        if address == self.base+m.SCENT_CALL_RVA and data != m.SCENT_ORIGINAL_CALL and self.failure == "scent_partial":
            self.failure = None; self.put(address, data[:2]); raise OSError("partial scent patch")
        if address == self.allocation+m.CODE_SIZE+72 and self.failure == "publish":
            self.failure = None; self.put(address, data[:8]); raise OSError("partial lease")
        if address == self.allocation+0x40000+m.CODE_SIZE+72 and self.failure == "vision_publish":
            self.failure = None; self.put(address, data[:8]); raise OSError("partial visual lease")
        if address == self.allocation+0x80000+m.CODE_SIZE+72 and self.failure == "scent_publish":
            self.failure = None; self.put(address, data[:8]); raise OSError("partial scent lease")
        self.put(address, data)

    def protect(self, address, size, protection):
        self.events.append(("protect", address, protection)); return 0x20

    def flush(self, address, size):
        self.events.append(("flush", address))
        if address == self.base+m.CALL_RVA and self.failure == "flush":
            self.failure = None; raise OSError("cache flush")
        if address == self.base+m.VISION_CALL_RVA and self.failure == "vision_flush":
            self.failure = None; raise OSError("visual cache flush")
        if address == self.base+m.SCENT_CALL_RVA and self.failure == "scent_flush":
            self.failure = None; raise OSError("scent cache flush")

    def allocate_near(self, site):
        allocation = self.allocation+sum(e[0] == "allocate" for e in self.events)*0x40000
        self.events.append(("allocate",)); return allocation

    def clock(self):
        return 1000, 1000

    def is_running(self):
        return self.running

    @contextmanager
    def frozen_threads(self, site, size):
        self.events.append(("suspend",))
        try:
            if self.failure == "context":
                raise OSError("thread context")
            if self.failure == "vision_context" and site == self.base+m.VISION_CALL_RVA:
                raise OSError("visual thread context")
            if self.failure == "scent_context" and site == self.base+m.SCENT_CALL_RVA:
                raise OSError("scent thread context")
            yield
        finally:
            self.events.append(("resume",))


def put_u32(api, address, value):
    api.put(address, struct.pack("<I", value))


def put_qword(api, address, value):
    api.put(address, struct.pack("<Q", value))


def fixture(api, mounted=False):
    objects = 0x200000000
    world, local_manager, local_slot = objects, objects+0x1000, objects+0x2000
    char, player, entities, pool = objects+0x4000, objects+0x8000, objects+0x10000, objects+0x18000
    nodes, mapping, index, slot, generation = objects+0x19000, objects+0x22000, 3, 7, 0x1234
    source, handle = nodes+slot*0x180, (index << 16)|generation
    put_qword(api, api.base+m.WORLD_RVA, world)
    put_u32(api, world+0x48, 7); api.put(world+0x7C, b"\1")
    put_qword(api, api.base+m.LOCAL_RVA, local_manager)
    put_qword(api, local_manager+0x60, local_slot)
    put_qword(api, local_slot+0x170, char)
    put_qword(api, char, api.base+m.CHAR_VTABLE_RVA)
    put_qword(api, char+0x2400, player+0x10)
    put_u32(api, char+0x2098, handle)
    put_qword(api, player, api.base+m.PLAYER_VTABLE_RVA)
    put_qword(api, player+0x68, char)
    put_qword(api, api.base+m.ENTITY_RVA, entities)
    put_qword(api, entities+0x20290, pool)
    put_qword(api, pool, nodes); put_qword(api, pool+8, mapping)
    put_u32(api, pool+0x120, 64)
    put_u32(api, mapping+index*4, (slot << 16)|generation)
    put_qword(api, source+0xB8, char)
    put_u32(api, source+0x170, 1)
    api.put(source+0x174, struct.pack("<H", index))
    put_u32(api, source+0x17C, 1)
    vehicle, vehicle_source, vehicle_handle = objects+0x28000, nodes+8*0x180, (4 << 16)|0x5678
    if mounted:
        put_u32(api, source+0x120, 0x7548E735); api.put(source+0x124, b"\x02")
        put_qword(api, pool+0x50, objects+0x23000)
        api.put(pool+0x58, struct.pack("<H", 1)); api.put(objects+0x23000, struct.pack("<H", 8))
        put_qword(api, vehicle, api.base+m.VEHICLE_VTABLE_RVA)
        put_qword(api, vehicle+8, api.base+m.VEHICLE_INTERFACE_RVA)
        put_u32(api, vehicle+0x4A28, vehicle_handle); put_u32(api, vehicle+0x5020, 0x7548E735)
        put_qword(api, vehicle_source+0x40, vehicle+8); put_u32(api, vehicle_source+0x54, handle)
        put_u32(api, vehicle_source+0x170, 2); put_u32(api, vehicle_source+0x17C, 1)
        api.put(vehicle_source+0x174, struct.pack("<H", 4))
        put_u32(api, mapping+16, (8 << 16)|0x5678)
    game = types.SimpleNamespace(base=api.base, pid=123, exe=types.SimpleNamespace(read_bytes=lambda: b"fake ninja game"))
    binding = dict(character=char, source=source, handle=handle, pool=pool, player=player, mapping=mapping)
    return game, binding, dict(world=world, local_manager=local_manager, local_slot=local_slot, nodes=nodes,
                               index=index, slot=slot, generation=generation, entities=entities,
                               vehicle=vehicle, vehicle_source=vehicle_source, vehicle_handle=vehicle_handle)


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeAPI(); self.game, self.binding, self.extra = fixture(self.api)
        self.hash_patch = patch.object(m.probe, "EXPECTED_SHA256", hashlib.sha256(b"fake ninja game").hexdigest())
        self.hash_patch.start(); self.addCleanup(self.hash_patch.stop)
        self.mode = m.NinjaMode(self.game, 1, api=self.api)

    def test_source_binding_install_disable_reuse(self):
        self.assertEqual(self.mode._binding(), self.binding)
        self.assertEqual(self.mode.publish(), 1)
        self.assertEqual(self.api.read(self.mode.site, 5), m.rel_call(self.mode.site, self.api.allocation))
        header = self.api.allocation+m.CODE_SIZE
        self.assertEqual(struct.unpack("<Q", self.api.read(header+72, 8))[0], 1300)
        self.mode.disable(); self.mode.close()
        self.assertEqual(self.api.read(header+72, 56), bytes(56))
        other = m.NinjaMode(self.game, 1, api=self.api)
        self.assertEqual(other.publish(), 1)
        self.assertEqual(sum(e[0] == "allocate" for e in self.api.events), 3)
        self.assertEqual(other.vision_allocation, self.mode.vision_allocation)
        self.assertEqual(other.scent_allocation, self.mode.scent_allocation)

    def test_fail_closed_after_world_generation_or_player_rebinding(self):
        self.mode.publish()
        cases = [(self.extra["world"]+0x48, struct.pack("<I", 0)),
                 (self.binding["mapping"]+12, struct.pack("<I", (7 << 16)|0x1235)),
                 (self.binding["player"]+0x68, struct.pack("<Q", 0))]
        for address, invalid in cases:
            with self.subTest(address=address):
                original = self.api.read(address, len(invalid)); self.api.put(address, invalid)
                with self.assertRaises(RuntimeError):
                    self.mode.publish()
                self.assertEqual(self.api.read(self.api.allocation+m.CODE_SIZE+72, 8), bytes(8))
                self.api.put(address, original)
                self.mode.publish()

    def test_current_vehicle_flags_do_not_change_local_identity_filter(self):
        put_u32(self.api, self.binding["source"]+0x120, 0x7548E735)
        self.api.put(self.binding["source"]+0x124, b"\2")
        self.assertEqual(self.mode._binding(), self.binding)
        self.assertEqual(self.mode.publish(), 1)
        self.assertIsNone(self.mode.last_vehicle_binding)  # No driver binding.
        api = FakeAPI(); game, binding, extra = fixture(api, mounted=True)
        mode = m.NinjaMode(game, 1, api=api)
        self.assertEqual(mode.publish(), 1)
        self.assertEqual(mode.last_vehicle_binding["source"], extra["vehicle_source"])
        # Engine-off vehicles still have an AI visual contribution.
        api.put(binding["source"]+0x124, b"\0")
        self.assertEqual(mode.publish(), 1)

    def test_install_errors_rollback_before_resume(self):
        for failure in ("partial", "flush", "context"):
            with self.subTest(failure=failure):
                api = FakeAPI(); game, _, _ = fixture(api); api.failure = failure
                mode = m.NinjaMode(game, 1, api=api)
                with self.assertRaises((OSError, RuntimeError)):
                    mode.publish()
                self.assertEqual(api.read(mode.site, 5), m.ORIGINAL_CALL)
                self.assertEqual(api.events[-1], ("resume",))

    def test_lease_write_failure_and_game_exit_cleanup(self):
        self.mode.publish(); self.api.failure = "publish"
        with self.assertRaises(OSError):
            self.mode.publish()
        self.assertEqual(self.api.read(self.api.allocation+m.CODE_SIZE+72, 8), bytes(8))
        self.api.running = False
        self.mode.close(); self.mode.close()
        self.assertIsNone(self.mode.allocation)
        self.assertIsNone(self.mode.vision_allocation)
        self.assertIsNone(self.mode.scent_allocation)

    def test_foreign_code_binary_and_owned_metadata_rejected(self):
        self.api.put(self.mode.site, b"\x90"*5)
        with self.assertRaises(RuntimeError):
            self.mode.publish()
        self.assertFalse(any(e[0] == "allocate" for e in self.api.events))
        self.api.put(self.mode.site, m.ORIGINAL_CALL)
        self.mode.publish(); self.api.put(self.api.allocation+m.CODE_SIZE, b"X")
        other = m.NinjaMode(self.game, 1, api=self.api)
        with self.assertRaises(RuntimeError):
            other.publish()
        with self.assertRaises(ValueError):
            m.NinjaMode(self.game, 1, api=self.api, code=bytes(m.CODE_SIZE))

    def test_wrong_engine_signature_prevents_install(self):
        self.api.put(self.game.base+m.ORIGINAL_RVA, b"X")
        with self.assertRaises(RuntimeError):
            self.mode.publish()
        self.assertFalse(self.api.events)

    def test_existing_hearing_v1_is_reused_without_replacing_code(self):
        self.mode._install()  # exactly the installed V1 contract, no vision yet
        original_code = self.api.read(self.mode.allocation, m.CODE_SIZE)
        self.assertEqual(hashlib.sha256(original_code).hexdigest(), m.STUB_SHA256)
        self.mode._publish(self.binding, 1300)
        other = m.NinjaMode(self.game, 1, api=self.api)
        other.publish()
        self.assertEqual(other.allocation, self.mode.allocation)
        self.assertNotEqual(other.vision_allocation, other.allocation)
        self.assertEqual(self.api.read(other.allocation, m.CODE_SIZE), original_code)
        self.assertEqual(sum(e[0] == "allocate" for e in self.api.events), 3)
        other.disable()
        for allocation in (other.allocation, other.vision_allocation, other.scent_allocation):
            self.assertEqual(self.api.read(allocation+m.CODE_SIZE+72, 8), bytes(8))

    def test_visual_install_or_publish_failure_disables_both_leases(self):
        for failure in ("vision_partial", "vision_flush", "vision_context", "vision_publish"):
            with self.subTest(failure=failure):
                api = FakeAPI(); game, _, _ = fixture(api)
                mode = m.NinjaMode(game, 1, api=api)
                api.failure = failure
                with self.assertRaises((RuntimeError, OSError)):
                    mode.publish()
                self.assertEqual(api.read(mode.allocation+m.CODE_SIZE+72, 8), bytes(8))
                if mode.vision_allocation is None:
                    self.assertEqual(api.read(mode.vision_site, 5), m.VISION_ORIGINAL_CALL)
                else:
                    self.assertEqual(api.read(mode.vision_allocation+m.CODE_SIZE+72, 8), bytes(8))
                self.assertEqual(sum(e[0] == "suspend" for e in api.events),
                                 sum(e[0] == "resume" for e in api.events))

    def test_scent_install_publish_and_disable_errors_expire_all_three_leases(self):
        for failure in ("scent_partial", "scent_flush", "scent_context", "scent_publish"):
            with self.subTest(failure=failure):
                api = FakeAPI(); game, _, _ = fixture(api)
                mode = m.NinjaMode(game, 1, api=api); api.failure = failure
                with self.assertRaises((RuntimeError, OSError)):
                    mode.publish()
                for allocation in (mode.allocation, mode.vision_allocation, mode.scent_allocation):
                    if allocation is not None:
                        self.assertEqual(api.read(allocation+m.CODE_SIZE+72, 8), bytes(8))
                if mode.scent_allocation is None:
                    self.assertEqual(api.read(mode.scent_site, 5), m.SCENT_ORIGINAL_CALL)
                self.assertEqual(sum(e[0] == "suspend" for e in api.events),
                                 sum(e[0] == "resume" for e in api.events))
        self.mode.publish(); self.api.failure = "scent_publish"
        with self.assertRaises(OSError):self.mode.disable()
        for allocation in (self.mode.allocation, self.mode.vision_allocation, self.mode.scent_allocation):
            self.assertEqual(self.api.read(allocation+m.CODE_SIZE+72, 8), bytes(8))

    def test_scent_foreign_tamper_version_and_old_two_pages_reuse(self):
        self.mode._install(); self.mode._install(vision=True)
        old = [self.api.read(a, m.CODE_SIZE+256) for a in
               (self.mode.allocation, self.mode.vision_allocation)]
        fresh = m.NinjaMode(self.game, 1, api=self.api); fresh.publish(); fresh.disable()
        self.assertEqual(fresh.allocation, self.mode.allocation)
        self.assertEqual(fresh.vision_allocation, self.mode.vision_allocation)
        for previous, allocation in zip(old, (fresh.allocation, fresh.vision_allocation)):
            actual = self.api.read(allocation, m.CODE_SIZE+256)
            self.assertEqual(actual[:m.CODE_SIZE+64], previous[:m.CODE_SIZE+64])
            self.assertEqual(actual[m.CODE_SIZE+128:], previous[m.CODE_SIZE+128:])
        self.assertEqual(sum(e[0] == "allocate" for e in self.api.events), 3)
        for location in (fresh.scent_site, fresh.scent_allocation, fresh.scent_allocation+m.CODE_SIZE):
            original = self.api.read(location, 1); self.api.put(location, b"X")
            with self.assertRaises(RuntimeError):fresh.publish()
            for allocation in (fresh.allocation, fresh.vision_allocation, fresh.scent_allocation):
                self.assertEqual(self.api.read(allocation+m.CODE_SIZE+72, 8), bytes(8))
            self.api.put(location, original)
        for rva in (m.SCENT_ORIGINAL_RVA, 0x612C57, 0x612C80):
            api = FakeAPI(); game, _, _ = fixture(api); api.put(api.base+rva, b"X")
            with self.assertRaises(RuntimeError):m.NinjaMode(game, 1, api=api).publish()
            self.assertFalse(any(e[0] == "allocate" for e in api.events))

    def test_dismounted_vehicle_clears_header_and_foreign_patch_is_rejected(self):
        api = FakeAPI(); game, binding, extra = fixture(api, mounted=True)
        mode = m.NinjaMode(game, 1, api=api)
        mode.publish()
        put_u32(api, extra["vehicle_source"]+0x54, 0)
        self.assertEqual(mode.publish(), 1)  # Dismounted, stale ID/audio hints.
        self.assertIsNone(mode.last_vehicle_binding)
        for allocation in (mode.allocation, mode.vision_allocation, mode.scent_allocation):
            self.assertEqual(struct.unpack("<Q", api.read(allocation+m.CODE_SIZE+72, 8))[0], 1300)
        self.assertEqual(api.read(mode.vision_allocation+m.CODE_SIZE+256, 32), bytes(32))
        fresh = FakeAPI(); game, _, _ = fixture(fresh)
        mode = m.NinjaMode(game, 1, api=fresh)
        fresh.put(mode.vision_site, b"\x90"*5)
        with self.assertRaises(RuntimeError):
            mode.publish()
        self.assertFalse(fresh.events)

    def test_dismount_residual_hints_and_remount_publish_fresh_vehicle(self):
        api = FakeAPI(); game, binding, extra = fixture(api, mounted=True)
        mode = m.NinjaMode(game, 1, api=api)
        mode.publish()
        vehicle = dict(mode.last_vehicle_binding)
        put_u32(api, extra["vehicle_source"]+0x54, 0)
        # Neither lingering vehicle definition nor an audio bit is a driver.
        for audio in (2, 0, 2):
            api.put(binding["source"]+0x124, bytes([audio]))
            self.assertEqual(mode.publish(), 1)
            self.assertIsNone(mode.last_vehicle_binding)
            self.assertEqual(api.read(mode.vision_allocation+m.CODE_SIZE+256, 32), bytes(32))
        put_u32(api, extra["vehicle_source"]+0x54, binding["handle"])
        self.assertEqual(mode.publish(), 1)
        self.assertEqual(mode.last_vehicle_binding, vehicle)

    def test_vehicle_transition_expires_both_leases_then_requires_fresh_binding(self):
        api = FakeAPI(); game, binding, extra = fixture(api, mounted=True)
        mode = m.NinjaMode(game, 1, api=api)
        mode.publish()
        put_u32(api, binding["mapping"]+16, (8 << 16)|0x5679)
        with self.assertRaises(m.TransientNinjaState):
            mode.publish()
        for allocation in (mode.allocation, mode.vision_allocation, mode.scent_allocation):
            self.assertEqual(api.read(allocation+m.CODE_SIZE+72, 8), bytes(8))
        self.assertIsNone(mode.last_binding)
        put_u32(api, binding["mapping"]+16, (8 << 16)|0x5678)
        self.assertEqual(mode.publish(), 1)
        # A driver change during the record read is a transition, too.
        original_read = api.read
        def change_driver(address, size):
            data = original_read(address, size)
            if address == extra["vehicle_source"] and size == 0x180:
                put_u32(api, extra["vehicle_source"]+0x54, 0)
            return data
        with patch.object(api, "read", side_effect=change_driver):
            with self.assertRaises(m.TransientNinjaState):
                mode.publish()
        for allocation in (mode.allocation, mode.vision_allocation, mode.scent_allocation):
            self.assertEqual(api.read(allocation+m.CODE_SIZE+72, 8), bytes(8))
        self.assertEqual(mode.publish(), 1)
        self.assertIsNone(mode.last_vehicle_binding)

    def test_actor_rebinding_waits_but_global_and_write_errors_stay_fatal(self):
        self.mode.publish()
        transitions = [(self.game.base+m.LOCAL_RVA, bytes(8)),
                       (self.extra["local_manager"]+0x60, bytes(8)),
                       (self.extra["local_slot"]+0x170, bytes(8)),
                       (self.binding["character"]+0x2400, bytes(8)),
                       (self.binding["player"]+0x68, bytes(8)),
                       (self.binding["character"]+0x2098, bytes(4)),
                       (self.binding["source"]+0x17C, bytes(4))]
        for address, data in transitions:
            with self.subTest(address=address):
                original = self.api.read(address, len(data)); self.api.put(address, data)
                with self.assertRaises(m.TransientNinjaState):
                    self.mode.publish()
                for allocation in (self.mode.allocation, self.mode.vision_allocation, self.mode.scent_allocation):
                    self.assertEqual(self.api.read(allocation+m.CODE_SIZE+72, 8), bytes(8))
                self.api.put(address, original)
                self.assertEqual(self.mode.publish(), 1)
        for address, data in ((self.extra["world"]+0x48, bytes(4)),
                              (self.binding["pool"]+0x120, bytes(4)),
                              (self.mode.vision_site, b"\x90"*5)):
            with self.subTest(fatal_address=address):
                original = self.api.read(address, len(data)); self.api.put(address, data)
                with self.assertRaises(RuntimeError) as raised:
                    self.mode.publish()
                self.assertNotIsInstance(raised.exception, m.TransientNinjaState)
                self.api.put(address, original)
                self.mode.publish()
        self.api.failure = "publish"
        with self.assertRaises(OSError):
            self.mode.publish()
        self.mode.publish()
        put_u32(self.api, self.binding["mapping"]+12, (7 << 16)|0x1235)
        self.api.failure = "publish"  # Failure while expiring a transition.
        with self.assertRaises(OSError):
            self.mode.publish()
        self.assertEqual(self.api.read(self.mode.vision_allocation+m.CODE_SIZE+72, 8), bytes(8))


class MachineTests(unittest.TestCase):
    def execute(self, *, active=True, mounted=False, condition=None, event=7.0):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
        from unicorn import x86_const as x
        api = FakeAPI(); game, binding, extra = fixture(api, mounted)
        mode = m.NinjaMode(game, 1, api=api)
        uc = Uc(UC_ARCH_X86, UC_MODE_64)
        uc.mem_map(api.base, 0x3000000); uc.mem_map(api.allocation, m.ALLOCATION_SIZE)
        uc.mem_map(0x200000000, 0x40000); uc.mem_map(0x300000000, 0x10000)
        for address, byte in api.memory.items():
            uc.mem_write(address, bytes([byte]))
        uc.mem_write(api.allocation, mode.code)
        header = api.allocation+m.CODE_SIZE
        uc.mem_write(header, mode._header())
        uc.mem_write(header+64, struct.pack("<Q", 2))
        uc.mem_write(header+72, struct.pack("<7Q", 1300 if active else 0, *(binding[k] for k in ("character", "source", "handle", "pool", "player", "mapping"))))
        qpc = api.base+0x1000
        uc.mem_write(api.base+m.QPC_IAT_RVA, struct.pack("<Q", qpc))
        uc.mem_write(qpc, b"\xc3"); uc.mem_write(api.base+m.ORIGINAL_RVA, b"\xc3")
        continuation = api.base+m.CALL_RVA+5
        caller_code = m.SIGNATURES[0x5EC971]
        uc.mem_write(continuation, caller_code)
        caller_sp = 0x300008000
        uc.mem_write(caller_sp-8, struct.pack("<Q", continuation))
        uc.mem_write(caller_sp+0xB0, bytes.fromhex("77"*16))
        uc.mem_write(caller_sp+0x90, bytes.fromhex("99"*16))
        uc.reg_write(x.UC_X86_REG_RSP, caller_sp-8)
        source = binding["source"]
        if condition == "npc":
            source += 0x180
        nonvolatile = {x.UC_X86_REG_RBX: 0xBBB, x.UC_X86_REG_RBP: 0xB0B, x.UC_X86_REG_RDI: 0xD1D,
                       x.UC_X86_REG_RSI: source, x.UC_X86_REG_R12: 0x1212, x.UC_X86_REG_R13: 0x1313,
                       x.UC_X86_REG_R14: 0x202000000, x.UC_X86_REG_R15: 0x1515}
        for register, value in nonvolatile.items():
            uc.reg_write(register, value)
        uc.reg_write(x.UC_X86_REG_RCX, 0x202000000); uc.reg_write(x.UC_X86_REG_RDX, 2)
        uc.reg_write(x.UC_X86_REG_R8, 0x200030000)
        def float_bits(value):
            return struct.unpack("<I", struct.pack("<f", value))[0]
        for n in range(16):
            uc.reg_write(getattr(x, "UC_X86_REG_XMM"+str(n)), 0x555500000000+n)
        uc.reg_write(x.UC_X86_REG_XMM6, float_bits(2))
        uc.reg_write(x.UC_X86_REG_XMM7, float_bits(3))
        uc.reg_write(x.UC_X86_REG_XMM9, float_bits(5))
        original_nonvolatile_xmm = {n: uc.reg_read(getattr(x, "UC_X86_REG_XMM"+str(n))) for n in range(6, 16)}
        mutations = {
            "expired": (header+72, struct.pack("<Q", 1000)),
            "odd": (header+64, struct.pack("<Q", 3)),
            "world": (extra["world"]+0x48, bytes(4)),
            "owner": (binding["source"]+0xB8, bytes(8)),
            "type": (binding["source"]+0x170, struct.pack("<I", 2)),
            "inactive": (binding["source"]+0x17C, bytes(4)),
            "generation": (binding["mapping"]+12, struct.pack("<I", (7 << 16)|0x1235)),
            "slot": (binding["mapping"]+12, struct.pack("<I", (8 << 16)|0x1234)),
            "map_index": (binding["source"]+0x174, struct.pack("<H", 4)),
            "handle": (binding["character"]+0x2098, struct.pack("<I", 0x31235)),
            "new_character": (extra["local_slot"]+0x170, struct.pack("<Q", binding["character"]+8)),
            "player_link": (binding["character"]+0x2400, bytes(8)),
            "player_backlink": (binding["player"]+0x68, bytes(8)),
            "player_vtable": (binding["player"], bytes(8)),
            "pool": (extra["entities"]+0x20290, bytes(8)),
            "mapping": (binding["pool"]+8, bytes(8)),
            "capacity": (binding["pool"]+0x120, struct.pack("<I", 3)),
        }
        if condition in mutations:
            uc.mem_write(*mutations[condition])
        volatile_registers = (x.UC_X86_REG_RAX, x.UC_X86_REG_RCX, x.UC_X86_REG_RDX,
                              x.UC_X86_REG_R8, x.UC_X86_REG_R9, x.UC_X86_REG_R10, x.UC_X86_REG_R11)
        expected_gpr = {r: r+0x100000 for r in volatile_registers}
        expected_xmm = {n: float_bits(event) | (0xABCDEF << 64) if n == 0 else n+0xABCDEF for n in range(6)}
        calls, writes, return_state = [], [], {}
        def hook(cpu, address, size, unused):
            if address == api.base+m.ORIGINAL_RVA:
                calls.append("original")
                self.assertEqual(cpu.reg_read(x.UC_X86_REG_RSP) % 16, 8)
                self.assertEqual(cpu.reg_read(x.UC_X86_REG_RCX), 0x202000000)
                self.assertEqual(cpu.reg_read(x.UC_X86_REG_RDX), 2)
                self.assertEqual(cpu.reg_read(x.UC_X86_REG_R8), 0x200030000)
                for reg, value in expected_gpr.items():
                    cpu.reg_write(reg, value)
                for n, value in expected_xmm.items():
                    cpu.reg_write(getattr(x, "UC_X86_REG_XMM"+str(n)), value)
            elif address == qpc:
                calls.append("qpc")
                self.assertEqual(cpu.reg_read(x.UC_X86_REG_RSP) % 16, 8)
                cpu.mem_write(cpu.reg_read(x.UC_X86_REG_RCX), struct.pack("<Q", 1000))
                for reg in expected_gpr:
                    cpu.reg_write(reg, 0xFEFE)
                for n in range(6):
                    cpu.reg_write(getattr(x, "UC_X86_REG_XMM"+str(n)), 0xFEFE)
                cpu.reg_write(x.UC_X86_REG_RAX, 0 if condition == "qpc_fail" else 1)
                if condition == "sequence_race":
                    cpu.mem_write(header+64, struct.pack("<Q", 4))
            elif address == continuation:
                return_state["gpr"] = {r: cpu.reg_read(r) for r in expected_gpr}
                return_state["nonvolatile"] = {r: cpu.reg_read(r) for r in nonvolatile}
                return_state["xmm"] = {n: cpu.reg_read(getattr(x, "UC_X86_REG_XMM"+str(n))) for n in range(16)}
                return_state["rsp"] = cpu.reg_read(x.UC_X86_REG_RSP)
            elif address == continuation+len(caller_code):
                cpu.emu_stop()
        def on_write(cpu, access, address, size, value, unused):
            if not 0x300000000 <= address < 0x300010000:
                writes.append((address, size))
        uc.hook_add(UC_HOOK_CODE, hook); uc.hook_add(UC_HOOK_MEM_WRITE, on_write)
        uc.emu_start(api.allocation, continuation+len(caller_code), count=10000)
        self.assertTrue(return_state)
        self.assertEqual(return_state["gpr"], expected_gpr)
        self.assertEqual(return_state["nonvolatile"], nonvolatile)
        self.assertEqual(return_state["rsp"], caller_sp)
        self.assertEqual({n: return_state["xmm"][n] for n in range(6)}, expected_xmm)
        for n in (8, 9, 10, 11, 12, 13, 14, 15):
            self.assertEqual(return_state["xmm"][n], original_nonvolatile_xmm[n])
        self.assertEqual(calls.count("original"), 1)
        self.assertTrue(all(header+256 <= a and a+n <= header+320 for a, n in writes))
        result = struct.unpack("<f", struct.pack("<I", uc.reg_read(x.UC_X86_REG_XMM14) & 0xFFFFFFFF))[0]
        return uc, return_state, result, calls, header

    def test_active_on_foot_and_atv_remove_only_movement_addend(self):
        from unicorn import x86_const as x
        for mounted in (False, True):
            with self.subTest(mounted=mounted):
                uc, state, result, calls, header = self.execute(mounted=mounted)
                self.assertEqual(result, 7)
                self.assertEqual(state["xmm"][6], 0); self.assertEqual(state["xmm"][7], 0)
                self.assertEqual(struct.unpack("<Q", uc.mem_read(header+264, 8))[0], 1)
                self.assertEqual(struct.unpack("<4f", uc.mem_read(header+288, 16)), (7, 2, 3, 15))

    def test_original_event_zero_and_nonzero_are_preserved(self):
        for event in (0., 7., 150.):
            self.assertEqual(self.execute(event=event)[2], event)
            self.assertEqual(self.execute(active=False, event=event)[2], event+15)

    def test_off_expired_npc_invalid_binding_and_races_default(self):
        cases = [None, "expired", "npc", "odd", "world", "owner", "type", "inactive", "generation", "slot",
                 "map_index", "handle", "new_character", "player_link", "player_backlink", "player_vtable", "pool",
                 "mapping", "capacity", "qpc_fail", "sequence_race"]
        for condition in cases:
            with self.subTest(condition=condition):
                uc, state, result, calls, header = self.execute(active=condition is not None, condition=condition)
                self.assertEqual(result, 22)
                self.assertEqual(state["xmm"][6], struct.unpack("<I", struct.pack("<f", 2))[0])
                self.assertEqual(state["xmm"][7], struct.unpack("<I", struct.pack("<f", 3))[0])
                self.assertEqual(struct.unpack("<Q", uc.mem_read(header+272, 8))[0], 1)

    def test_hash_and_instruction_boundaries(self):
        from capstone import Cs, CS_ARCH_X86, CS_MODE_64
        code = Path(m.__file__).with_name("ninja_stub.bin").read_bytes()
        self.assertEqual(len(code), m.BUNDLE_SIZE)
        self.assertEqual(hashlib.sha256(code[:m.CODE_SIZE]).hexdigest(), m.STUB_SHA256)
        self.assertEqual(hashlib.sha256(code[m.CODE_SIZE:m.CODE_SIZE*2]).hexdigest(), m.VISION_STUB_SHA256)
        self.assertEqual(hashlib.sha256(code[m.CODE_SIZE*2:]).hexdigest(), m.SCENT_STUB_SHA256)
        instructions = list(Cs(CS_ARCH_X86, CS_MODE_64).disasm(code[:m.CODE_SIZE].rstrip(b"\0"), 0))
        self.assertEqual(instructions[0].mnemonic, "sub")
        self.assertEqual(instructions[1].mnemonic, "call")


class VisionMachineTests(unittest.TestCase):
    def execute(self, *, target="player", active=True, condition=None, score=.75):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
        from unicorn import x86_const as x
        api = FakeAPI(); game, binding, extra = fixture(api, mounted=True)
        mode = m.NinjaMode(game, 1, api=api)
        vehicle = mode._vehicle_binding(binding)
        uc = Uc(UC_ARCH_X86, UC_MODE_64)
        uc.mem_map(api.base, 0x3000000); uc.mem_map(api.allocation, m.ALLOCATION_SIZE)
        uc.mem_map(0x200000000, 0x40000); uc.mem_map(0x300000000, 0x10000)
        for address, byte in api.memory.items():
            uc.mem_write(address, bytes([byte]))
        uc.mem_write(api.allocation, mode.vision_code)
        header = api.allocation+m.CODE_SIZE
        uc.mem_write(header, mode._header(vision=True))
        uc.mem_write(header+64, struct.pack("<Q", 2))
        uc.mem_write(header+72, struct.pack("<7Q", 1300 if active else 0,
                     *(binding[k] for k in ("character", "source", "handle", "pool", "player", "mapping"))))
        uc.mem_write(header+256, struct.pack("<4Q", *(vehicle[k] for k in ("vehicle", "source", "handle", "vehicle_type"))))
        source = binding["source"] if target == "player" else vehicle["source"]
        if target in ("npc", "other_vehicle"):
            source = extra["nodes"]+9*0x180
        qpc, original, continuation = api.base+0x1000, api.base+m.VISION_ORIGINAL_RVA, api.base+m.VISION_CALL_RVA+5
        uc.mem_write(api.base+m.QPC_IAT_RVA, struct.pack("<Q", qpc))
        uc.mem_write(qpc, b"\xc3"); uc.mem_write(original, b"\xc3")
        caller_sp = 0x300008000
        uc.mem_write(caller_sp-8, struct.pack("<Q", continuation))
        # At the original call entry arg5 is entryRSP+28, not our own frame.
        uc.mem_write(caller_sp+0x20, struct.pack("<Q", source))
        uc.reg_write(x.UC_X86_REG_RSP, caller_sp-8)
        nonvolatile = {x.UC_X86_REG_RBX: source, x.UC_X86_REG_RBP: 0xB0B, x.UC_X86_REG_RDI: 0xD1D,
                       x.UC_X86_REG_RSI: 0x5151, x.UC_X86_REG_R12: 0x1212, x.UC_X86_REG_R13: 0x1313,
                       x.UC_X86_REG_R14: 0x1414, x.UC_X86_REG_R15: 0x1515}
        for reg, value in nonvolatile.items():
            uc.reg_write(reg, value)
        for reg, value in ((x.UC_X86_REG_RCX, 0x202000000), (x.UC_X86_REG_RDX, 2),
                           (x.UC_X86_REG_R8, 0x200030000), (x.UC_X86_REG_R9, 0x200031000)):
            uc.reg_write(reg, value)
        for n in range(16):
            uc.reg_write(getattr(x, "UC_X86_REG_XMM"+str(n)), n+0x123456789000)
        bits = lambda v: struct.unpack("<I", struct.pack("<f", v))[0]
        uc.reg_write(x.UC_X86_REG_XMM9, bits(5))
        nonvolatile_xmm = {n: uc.reg_read(getattr(x, "UC_X86_REG_XMM"+str(n))) for n in range(6, 16)}
        mutations = {
            "expired": (header+72, struct.pack("<Q", 1000)),
            "odd": (header+64, struct.pack("<Q", 3)),
            "world": (extra["world"]+0x48, bytes(4)),
            "owner": (binding["source"]+0xB8, bytes(8)),
            "local_type": (binding["source"]+0x170, struct.pack("<I", 2)),
            "local_inactive": (binding["source"]+0x17C, bytes(4)),
            "generation": (binding["mapping"]+12, struct.pack("<I", (7 << 16)|0x1235)),
            "player_rebinding": (extra["local_slot"]+0x170, bytes(8)),
            "player_backlink": (binding["player"]+0x68, bytes(8)),
            "vehicle_driver": (vehicle["source"]+0x54, bytes(4)),
            "vehicle_generation": (binding["mapping"]+16, struct.pack("<I", (8 << 16)|0x5679)),
            "vehicle_slot": (binding["mapping"]+16, struct.pack("<I", (9 << 16)|0x5678)),
            "vehicle_interface": (vehicle["source"]+0x40, bytes(8)),
            "vehicle_type": (vehicle["vehicle"]+0x5020, bytes(4)),
            "vehicle_vtable": (vehicle["vehicle"], bytes(8)),
            "vehicle_mapindex": (vehicle["source"]+0x174, bytes(2)),
            "vehicle_inactive": (vehicle["source"]+0x17C, bytes(4)),
        }
        if condition in mutations:
            uc.mem_write(*mutations[condition])
        volatile = (x.UC_X86_REG_RAX, x.UC_X86_REG_RCX, x.UC_X86_REG_RDX,
                    x.UC_X86_REG_R8, x.UC_X86_REG_R9, x.UC_X86_REG_R10, x.UC_X86_REG_R11)
        expected_gpr = {r: r+0xABC000 for r in volatile}
        expected_xmm = {n: bits(score)|(0xABCDEF0123456789 << 32) if n == 0 else n+0xBADC0FFEE for n in range(6)}
        calls, writes, state = [], [], {}
        def hook(cpu, address, size, unused):
            if address == original:
                calls.append("original")
                self.assertEqual(cpu.reg_read(x.UC_X86_REG_RSP) % 16, 8)
                for reg, value in ((x.UC_X86_REG_RCX, 0x202000000), (x.UC_X86_REG_RDX, 2),
                                   (x.UC_X86_REG_R8, 0x200030000), (x.UC_X86_REG_R9, 0x200031000)):
                    self.assertEqual(cpu.reg_read(reg), value)
                arg5 = struct.unpack("<Q", cpu.mem_read(cpu.reg_read(x.UC_X86_REG_RSP)+0x28, 8))[0]
                self.assertEqual(arg5, source)
                for reg, value in expected_gpr.items():
                    cpu.reg_write(reg, value)
                for n, value in expected_xmm.items():
                    cpu.reg_write(getattr(x, "UC_X86_REG_XMM"+str(n)), value)
            elif address == qpc:
                calls.append("qpc")
                self.assertEqual(cpu.reg_read(x.UC_X86_REG_RSP) % 16, 8)
                cpu.mem_write(cpu.reg_read(x.UC_X86_REG_RCX), struct.pack("<Q", 1000))
                for reg in volatile:
                    cpu.reg_write(reg, 0xFEFE)
                for n in range(6):
                    cpu.reg_write(getattr(x, "UC_X86_REG_XMM"+str(n)), 0xFEFE)
                cpu.reg_write(x.UC_X86_REG_RAX, 0 if condition == "qpc_fail" else 1)
                if condition == "sequence_race":
                    cpu.mem_write(header+64, struct.pack("<Q", 4))
                elif condition == "rebind_race":
                    cpu.mem_write(extra["local_slot"]+0x170, bytes(8))
                elif condition == "generation_race":
                    cpu.mem_write(binding["mapping"]+12, struct.pack("<I", (7 << 16)|0x1235))
                elif condition == "driver_race":
                    cpu.mem_write(vehicle["source"]+0x54, bytes(4))
            elif address == continuation:
                state["gpr"] = {r: cpu.reg_read(r) for r in volatile}
                state["nonvolatile"] = {r: cpu.reg_read(r) for r in nonvolatile}
                state["xmm"] = {n: cpu.reg_read(getattr(x, "UC_X86_REG_XMM"+str(n))) for n in range(16)}
                state["rsp"] = cpu.reg_read(x.UC_X86_REG_RSP)
            elif address == api.base+0x612F60:
                state["score"] = struct.unpack("<f", struct.pack("<I", cpu.reg_read(x.UC_X86_REG_XMM6)&0xFFFFFFFF))[0]
                cpu.emu_stop()
        def on_write(cpu, access, address, size, value, unused):
            if not 0x300000000 <= address < 0x300010000:
                writes.append((address, size))
        uc.hook_add(UC_HOOK_CODE, hook); uc.hook_add(UC_HOOK_MEM_WRITE, on_write)
        uc.emu_start(api.allocation, api.base+0x612F61, count=10000)
        self.assertTrue(state)
        self.assertEqual(calls.count("original"), 1)
        self.assertEqual(state["gpr"], expected_gpr)
        self.assertEqual(state["nonvolatile"], nonvolatile)
        self.assertEqual(state["rsp"], caller_sp)
        self.assertEqual({n: state["xmm"][n] for n in range(1, 6)}, {n: expected_xmm[n] for n in range(1, 6)})
        self.assertEqual({n: state["xmm"][n] for n in range(6, 16)}, nonvolatile_xmm)
        self.assertEqual(state["xmm"][0] >> 32, expected_xmm[0] >> 32)
        self.assertTrue(all(header+288 <= a and a+n <= header+352 for a, n in writes))
        stats = struct.unpack("<4Q2f3Q", uc.mem_read(header+288, 64))
        return state, stats

    def test_local_player_and_current_atv_visual_scalar_only(self):
        for target in ("player", "vehicle"):
            for score in (0., .75, 4.):
                with self.subTest(target=target, score=score):
                    state, stats = self.execute(target=target, score=score)
                    self.assertEqual(state["xmm"][0] & 0xFFFFFFFF, 0)
                    self.assertEqual(state["score"], 0)
                    self.assertEqual(stats[1:3], (1, 0) if target == "player" else (0, 1))
                    self.assertEqual(stats[4:6], (score, 0))

    def test_off_non_targets_invalid_identity_and_lease_races_preserve_score(self):
        cases = [("player", None, False), ("vehicle", None, False), ("npc", None, True),
                 ("other_vehicle", None, True)]
        cases += [(target, condition, True) for target in ("player", "vehicle")
                  for condition in ("expired", "odd", "world", "owner", "local_type", "local_inactive",
                                    "generation", "player_rebinding", "player_backlink", "qpc_fail",
                                    "sequence_race", "rebind_race", "generation_race")]
        cases += [("vehicle", condition, True) for condition in ("vehicle_driver", "vehicle_generation", "vehicle_slot",
                  "vehicle_interface", "vehicle_type", "vehicle_vtable", "vehicle_mapindex", "vehicle_inactive", "driver_race")]
        for target, condition, active in cases:
            with self.subTest(target=target, condition=condition, active=active):
                state, stats = self.execute(target=target, condition=condition, active=active)
                self.assertEqual(state["score"], 3.75)
                self.assertEqual(stats[1:4], (0, 0, 1))


class ScentMachineTests(unittest.TestCase):
    fixture_data = json.loads(Path(__file__).with_name("ninja_scent_fixture.json").read_text(encoding="utf8"))

    def execute(self, *, active=True, condition=None, target="player", receiver="wildlife",
                native=False, score=.75, posture=0, distance=10., wind=5., angle=0., eliminator=False):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
        from unicorn import x86_const as x
        api = FakeAPI(); game, binding, extra = fixture(api, mounted=True)
        mode = m.NinjaMode(game, 1, api=api)
        uc = Uc(UC_ARCH_X86, UC_MODE_64)
        uc.mem_map(api.base, 0x3000000); uc.mem_map(api.allocation, m.ALLOCATION_SIZE)
        uc.mem_map(0x200000000, 0x40000); uc.mem_map(0x300000000, 0x10000)
        for address, byte in api.memory.items():uc.mem_write(address, bytes([byte]))
        uc.mem_write(api.allocation, mode.scent_code)
        header = api.allocation+m.CODE_SIZE
        uc.mem_write(header, mode._header(scent=True))
        uc.mem_write(header+64, struct.pack("<Q", 2))
        uc.mem_write(header+72, struct.pack("<7Q", 1300 if active else 0,
                     *(binding[k] for k in ("character", "source", "handle", "pool", "player", "mapping"))))
        source = binding["source"] if target == "player" else extra["nodes"]+9*0x180
        host, observer, xyz, node, bucket, weather = [0x200030000+i*0x1000 for i in range(6)]
        uc.mem_write(host+0x20, struct.pack("<Q", host+0x800))
        uc.mem_write(host+0x30, struct.pack("<Q", bucket))
        uc.mem_write(bucket, struct.pack("<2Q", node, node)); uc.mem_write(node+0x10, struct.pack("<I", 42))
        for n, profile in enumerate(self.fixture_data['profiles']):
            uc.mem_write(node+0x174+n*40, struct.pack("<10f", *profile))
        uc.mem_write(xyz, struct.pack("<3f", distance, 0, 0))
        uc.mem_write(source+0xCC, bytes([min(posture, 2)]))
        uc.mem_write(source+0xD4, bytes([2 if posture == 3 else 0]))
        uc.mem_write(source+0xDC, struct.pack("<f", .5)); uc.mem_write(source+0xEC, struct.pack("<f", 1.))
        uc.mem_write(source+0x118, struct.pack("<Q", int(eliminator)))
        if eliminator:
            for offset in (0x12C, 0x140, 0x154):uc.mem_write(source+offset, struct.pack("<f", 1.))
        # Receiver identity never scopes filtering; a pet AI uses the same local source rule.
        uc.mem_write(observer+0xB8, struct.pack("<Q", 0xCA7100 if receiver == "pet" else 0xDEEA00))
        uc.mem_write(source+0x170, struct.pack("<I", 1 if target == "player" else 3))
        qpc, original, continuation = api.base+0x1000, api.base+m.SCENT_ORIGINAL_RVA, api.base+m.SCENT_CALL_RVA+5
        uc.mem_write(api.base+m.QPC_IAT_RVA, struct.pack("<Q", qpc)); uc.mem_write(qpc, b"\xc3")
        for rva, data in self.fixture_data['rip_data'].items():uc.mem_write(api.base+int(rva, 16), bytes.fromhex(data))
        for rva in (0x27C23D8, 0x27C5DB8):uc.mem_write(api.base+rva, struct.pack("<Q", weather))
        uc.mem_write(original, bytes.fromhex(self.fixture_data['original_hex']) if native else b"\xc3")
        uc.mem_write(continuation, bytes.fromhex(self.fixture_data['consumer_hex']))
        dependencies = {0x679550: ("rax", 0), 0x2CDB10: ("rax", weather), 0x2FC210: ("float", 10.),
                        0x5F4E60: ("float", 1.), 0x5F3D60: ("float", 1.), 0x5F11D0: ("float", 1.),
                        0xA85720: ("rax", 0), 0xA839C0: ("float", 0.)}
        for rva in dependencies:uc.mem_write(api.base+rva, b"\xc3")
        caller_sp = 0x300008000
        uc.mem_write(caller_sp-8, struct.pack("<Q", continuation))
        uc.mem_write(caller_sp+0x20, struct.pack("<3Q", xyz, observer, source))
        uc.reg_write(x.UC_X86_REG_RSP, caller_sp-8)
        registers = ("RAX", "RCX", "RDX", "R8", "R9", "R10", "R11", "RBX", "RBP", "RSI", "RDI", "R12", "R13", "R14", "R15")
        for n, name in enumerate(registers):uc.reg_write(getattr(x, 'UC_X86_REG_'+name), 0xABC000+n)
        for name, value in dict(RCX=host, RDX=42, RBX=source).items():uc.reg_write(getattr(x, 'UC_X86_REG_'+name), value)
        bits = lambda value: struct.unpack("<I", struct.pack("<f", value))[0]
        for n in range(16):uc.reg_write(getattr(x, 'UC_X86_REG_XMM'+str(n)), (0x123456789ABCDEF << 32)+n)
        for n, value in ((2, wind), (3, angle), (7, 0.), (8, 1.), (9, 1.5)):
            old = uc.reg_read(getattr(x, 'UC_X86_REG_XMM'+str(n)))
            uc.reg_write(getattr(x, 'UC_X86_REG_XMM'+str(n)), (old & ~0xFFFFFFFF)|bits(value))
        uc.reg_write(x.UC_X86_REG_EFLAGS, 0x246)
        def snapshot():
            return ([uc.reg_read(getattr(x, 'UC_X86_REG_'+n)) for n in registers],
                    [uc.reg_read(getattr(x, 'UC_X86_REG_XMM'+str(n))) for n in range(16)],
                    uc.reg_read(x.UC_X86_REG_EFLAGS))
        inputs = snapshot(); caller_bytes = bytes(uc.mem_read(caller_sp, 64))
        mutations = {
            "expired": (header+72, struct.pack("<Q", 1000)), "odd": (header+64, struct.pack("<Q", 3)),
            "world": (extra['world']+0x48, bytes(4)), "world_inactive": (extra['world']+0x7C, bytes(1)),
            "owner": (binding['source']+0xB8, bytes(8)), "type": (binding['source']+0x170, struct.pack('<I', 2)),
            "inactive": (binding['source']+0x17C, bytes(1)), "character_vtable": (binding['character'], bytes(8)),
            "generation": (binding['mapping']+12, struct.pack('<I', (7 << 16)|0x1235)),
            "slot": (binding['mapping']+12, struct.pack('<I', (8 << 16)|0x1234)),
            "source_index": (binding['source']+0x174, bytes(2)), "handle": (binding['character']+0x2098, bytes(4)),
            "local_manager": (api.base+m.LOCAL_RVA, bytes(8)), "local_slot": (extra['local_manager']+0x60, bytes(8)),
            "player_rebinding": (extra['local_slot']+0x170, bytes(8)), "player_link": (binding['character']+0x2400, bytes(8)),
            "player_backlink": (binding['player']+0x68, bytes(8)), "player_vtable": (binding['player'], bytes(8)),
            "entity_manager": (api.base+m.ENTITY_RVA, bytes(8)), "pool": (extra['entities']+0x20290, bytes(8)),
            "mapping": (binding['pool']+8, bytes(8)), "capacity": (binding['pool']+0x120, bytes(4)),
        }
        if condition in mutations:uc.mem_write(*mutations[condition])
        calls, state, writes = [], {}, []
        def hook(cpu, address, size, unused):
            if address == original:
                calls.append('original'); self.assertEqual(snapshot(), inputs)
                rsp = cpu.reg_read(x.UC_X86_REG_RSP); self.assertEqual(rsp % 16, 8)
                self.assertEqual(struct.unpack('<3Q', cpu.mem_read(rsp+0x28, 24)), (xyz, observer, source))
                state['native_return'] = struct.unpack('<Q', cpu.mem_read(rsp, 8))[0]
                if not native:
                    for n, name in enumerate(registers[:7]):cpu.reg_write(getattr(x, 'UC_X86_REG_'+name), 0xBEEF000+n)
                    for n in range(6):cpu.reg_write(getattr(x, 'UC_X86_REG_XMM'+str(n)), (0xABCDEF0123456789 << 32)|(bits(score) if n == 0 else n))
                    cpu.reg_write(x.UC_X86_REG_EFLAGS, 0x202)
            elif address == state.get('native_return'):
                state['expected'] = snapshot()
            elif address == qpc:
                calls.append('qpc'); self.assertEqual(cpu.reg_read(x.UC_X86_REG_RSP) % 16, 8)
                cpu.mem_write(cpu.reg_read(x.UC_X86_REG_RCX), struct.pack('<Q', 1000))
                for name in registers[:7]:cpu.reg_write(getattr(x, 'UC_X86_REG_'+name), 0xDEAD)
                for n in range(6):cpu.reg_write(getattr(x, 'UC_X86_REG_XMM'+str(n)), 0xDEAD)
                cpu.reg_write(x.UC_X86_REG_RAX, 0 if condition == 'qpc_fail' else 1)
                cpu.reg_write(x.UC_X86_REG_EFLAGS, 0x202)
                if condition == 'sequence_race':cpu.mem_write(header+64, struct.pack('<Q', 4))
                elif condition and condition.startswith('late_'):cpu.mem_write(*mutations[condition[5:]])
            elif address == continuation:
                state['returned'] = snapshot(); state['rsp'] = cpu.reg_read(x.UC_X86_REG_RSP)
            elif address in (api.base+0x612C9F, api.base+0x612CE2):
                state['contributes'] = address == api.base+0x612C9F
                cpu.emu_stop()
            elif address-api.base in dependencies:
                kind, value = dependencies[address-api.base]
                if kind == 'rax':cpu.reg_write(x.UC_X86_REG_RAX, value)
                else:cpu.reg_write(x.UC_X86_REG_XMM0, bits(value))
        uc.hook_add(UC_HOOK_CODE, hook)
        uc.hook_add(UC_HOOK_MEM_WRITE, lambda cpu, access, address, size, value, unused:writes.append((address, size)))
        uc.emu_start(api.allocation, 0, count=20000)
        self.assertEqual(calls.count('original'), 1)
        self.assertIn('returned', state); self.assertIn('contributes', state)
        self.assertEqual(state['returned'][0], state['expected'][0])
        self.assertEqual(state['returned'][1][1:], state['expected'][1][1:])
        self.assertEqual(state['returned'][1][0] >> 32, state['expected'][1][0] >> 32)
        self.assertEqual(state['returned'][2], state['expected'][2])
        self.assertEqual(state['rsp'], caller_sp)
        self.assertEqual(bytes(uc.mem_read(caller_sp, 64)), caller_bytes)
        self.assertTrue(all(0x300000000 <= address and address+size <= caller_sp
                            or header+256 <= address and address+size <= header+320 for address, size in writes), writes)
        stats = struct.unpack('<4Q2f3Q', uc.mem_read(header+256, 64))
        state['native_score'] = struct.unpack('<f', struct.pack('<I', state['expected'][1][0] & 0xFFFFFFFF))[0]
        state['score'] = struct.unpack('<f', struct.pack('<I', state['returned'][1][0] & 0xFFFFFFFF))[0]
        return state, stats

    def test_scent_scalar_only_all_seven_args_flags_and_pet_receiver(self):
        for receiver, score in itertools.product(('wildlife', 'pet'), (0., .75, 4.)):
            with self.subTest(receiver=receiver, score=score):
                state, stats = self.execute(receiver=receiver, score=score)
                self.assertEqual(state['score'], 0); self.assertFalse(state['contributes'])
                self.assertEqual(stats[:4], (1, 1, 0, 0)); self.assertEqual(stats[4:6], (score, 0))

    def test_scent_off_other_sources_binding_and_late_races_keep_native_score(self):
        cases = [(False, None, 'player'), (True, None, 'animal'), (True, None, 'other_player')]
        conditions = ('expired', 'odd', 'qpc_fail', 'world', 'world_inactive', 'owner', 'type', 'inactive',
                      'character_vtable', 'generation', 'slot', 'source_index', 'handle', 'local_manager',
                      'local_slot', 'player_rebinding', 'player_link', 'player_backlink', 'player_vtable',
                      'entity_manager', 'pool', 'mapping', 'capacity', 'sequence_race')
        conditions += tuple('late_'+name for name in conditions if name not in ('odd', 'qpc_fail', 'sequence_race', 'expired'))
        cases += [(True, condition, 'player') for condition in conditions]
        for active, condition, target in cases:
            with self.subTest(active=active, condition=condition, target=target):
                state, stats = self.execute(active=active, condition=condition, target=target)
                self.assertEqual(state['score'], .75); self.assertTrue(state['contributes'])
                self.assertEqual(stats[:4], (1, 0, 0, 1))

    def test_real_scent_math_wind_angle_distance_posture_and_native_consumer(self):
        positive = 0
        for posture, wind, angle, distance in itertools.product(range(4), (0., 5., 10.), (0., 30., 90.), (0., 50., 300.)):
            with self.subTest(posture=posture, wind=wind, angle=angle, distance=distance):
                off, _ = self.execute(native=True, active=False, posture=posture, wind=wind, angle=angle, distance=distance)
                on, _ = self.execute(native=True, posture=posture, wind=wind, angle=angle, distance=distance)
                self.assertEqual(off['score'], off['native_score'])
                profile = self.fixture_data['profiles'][posture]
                mix = min(max(wind, 0.), 10.)/10.
                zero_distance = profile[2]+(profile[6]-profile[2])*mix
                one_distance = profile[3]+(profile[7]-profile[3])*mix
                zero_angle = profile[4]+(profile[8]-profile[4])*mix
                one_angle = profile[5]+(profile[9]-profile[5])*mix
                distance_factor = min(max((zero_distance-distance)/(zero_distance-one_distance), 0.), 1.)
                angle_factor = min(max((zero_angle-angle)/(zero_angle-one_angle), 0.), 1.)
                expected = (profile[0]+(profile[1]-profile[0])*.5)*distance_factor*angle_factor
                self.assertAlmostEqual(off['score'], expected, places=6)
                self.assertEqual(off['contributes'], expected > 0)
                self.assertEqual(on['native_score'], off['native_score'])
                self.assertEqual(on['score'], 0); self.assertFalse(on['contributes'])
                positive += off['score'] > 0
        self.assertGreater(positive, 0)
        for target, receiver, eliminator in itertools.product(('player', 'animal'), ('wildlife', 'pet'), (False, True)):
            with self.subTest(target=target, receiver=receiver, eliminator=eliminator):
                state, _ = self.execute(native=True, target=target, receiver=receiver, eliminator=eliminator)
                self.assertGreater(state['native_score'], 0)
                self.assertEqual(state['score'], 0 if target == 'player' else state['native_score'])


if __name__ == "__main__":
    unittest.main()
