"""No game access: fake Windows boundary and the real PIC stub on Unicorn."""
import hashlib
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

import pet_outline as m
from test_ninja_mode import FakeAPI as BaseAPI, fixture as player_fixture, put_qword, put_u32


class FakeAPI(BaseAPI):
    def __init__(self):
        super().__init__()
        for rva, data in m.SIGNATURES.items():
            self.put(self.base+rva, data)
        self.put(self.base+m.CALL_RVA, m.ORIGINAL_CALL)

    def write(self, address, data):
        if address == self.base+m.CALL_RVA and data != m.ORIGINAL_CALL and self.failure == "pet_partial":
            self.failure = None; self.put(address, data[:2]); raise OSError("partial pet patch")
        super().write(address, data)

    def flush(self, address, size):
        if address == self.base+m.CALL_RVA and self.failure == "pet_flush":
            self.failure = None; raise OSError("pet flush")
        super().flush(address, size)


def fixture(api):
    game, local, extra = player_fixture(api)
    objects = 0x200000000
    dog_character, dog, meta = objects+0x30000, objects+0x34000, objects+0x36000
    owner_component, player_list = objects+0x38000, objects+0x3A000
    dog_source, dog_handle = extra["nodes"]+9*0x180, (5 << 16)|0x9ABC
    put_qword(api, extra["local_manager"]+0x40, player_list)
    put_qword(api, extra["local_manager"]+0x48, player_list+8)
    put_qword(api, player_list, extra["local_slot"])
    api.put(extra["local_slot"]+0x148, b"\0")
    put_qword(api, local["character"]+0x2AD0, owner_component)
    put_qword(api, owner_component+0x10, local["player"])
    api.put(local["pool"]+0x1A, struct.pack("<H", 10))
    put_qword(api, dog_character, api.base+m.CHAR_VTABLE_RVA)
    put_qword(api, dog_character+0x2AD8, dog)
    put_u32(api, dog_character+0x2098, dog_handle)
    put_qword(api, dog+0x18, dog_character)
    put_qword(api, dog+0xB0, meta); api.put(meta, b"\0\1")
    put_qword(api, dog_source+0xB8, dog_character)
    put_u32(api, dog_source+0x170, 1); api.put(dog_source+0x17C, b"\1")
    api.put(dog_source+0x174, struct.pack("<H", 5))
    put_u32(api, local["mapping"]+20, (9 << 16)|0x9ABC)
    settings, options = objects+0x40000, objects+0x42000
    put_qword(api, api.base+m.SETTINGS_RVA, settings)
    put_qword(api, settings+0x1020, options)
    put_u32(api, options+0x244, 1); put_u32(api, options+0x248, 15); put_u32(api, options+0x310, 1)
    extra.update(dog_character=dog_character, dog=dog, meta=meta, dog_source=dog_source,
                 dog_handle=dog_handle, settings=settings, options=options, owner_component=owner_component)
    return game, local, extra


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeAPI(); self.game, self.local, self.extra = fixture(self.api)
        change = patch.object(m.probe, "EXPECTED_SHA256", hashlib.sha256(b"fake ninja game").hexdigest())
        change.start(); self.addCleanup(change.stop)
        self.mode = m.PetOutlineKeeper(self.game, 1, api=self.api)

    def test_closed_binding_install_off_and_owned_reuse(self):
        self.assertEqual(self.mode.publish(), 1)
        self.assertEqual(self.mode.last_binding["dog"], self.extra["dog"])
        header = self.mode.allocation+m.CODE_SIZE
        self.assertEqual(struct.unpack("<Q", self.api.read(header+72, 8))[0], 1300)
        # Publishing only writes code/site or the private header. No game data.
        self.assertTrue(all(e[1] == self.mode.site or self.mode.allocation <= e[1] < self.mode.allocation+m.ALLOCATION_SIZE
                            for e in self.api.events if e[0] == "write"))
        self.mode.disable(); self.mode.close()
        self.assertEqual(self.api.read(header+72, 56), bytes(56))
        self.assertEqual(self.api.read(header+256, 64), bytes(64))
        other = m.PetOutlineKeeper(self.game, 1, api=self.api)
        self.assertEqual(other.publish(), 1)
        self.assertEqual(other.allocation, self.mode.allocation)
        self.assertEqual(sum(e[0] == "allocate" for e in self.api.events), 1)

    def test_local_pet_transition_expires_then_fresh_recovery(self):
        self.mode.publish()
        cases = [(self.extra["meta"], b"\1"), (self.extra["meta"]+1, b"\0"),
                 (self.extra["dog"]+0x18, bytes(8)),
                 (self.local["mapping"]+20, struct.pack("<I", (9 << 16)|0x9ABD)),
                 (self.extra["owner_component"]+0x10, bytes(8))]
        for address, data in cases:
            with self.subTest(address=address):
                old = self.api.read(address, len(data)); self.api.put(address, data)
                with self.assertRaises(m.TransientPetState):
                    self.mode.publish()
                self.assertEqual(self.api.read(self.mode.allocation+m.CODE_SIZE+72, 8), bytes(8))
                self.api.put(address, old); self.assertEqual(self.mode.publish(), 1)

    def test_partial_patch_flush_and_thread_failure_restore_original(self):
        for failure in ("pet_partial", "pet_flush", "context"):
            with self.subTest(failure=failure):
                api = FakeAPI(); game, _, _ = fixture(api); api.failure = failure
                mode = m.PetOutlineKeeper(game, 1, api=api)
                with self.assertRaises((RuntimeError, OSError)):
                    mode.publish()
                self.assertEqual(api.read(mode.site, 5), m.ORIGINAL_CALL)
                self.assertEqual(api.events[-1], ("resume",))

    def test_version_foreign_code_and_owned_tampering_are_fatal(self):
        with patch.object(self.game.exe, "read_bytes", return_value=b"different game"):
            with self.assertRaises(RuntimeError):
                self.mode.publish()
        self.assertFalse(self.api.events)
        self.api.put(self.mode.site, b"\x90"*5)
        with self.assertRaises(RuntimeError):
            self.mode.publish()
        self.assertFalse(self.api.events)
        self.api.put(self.mode.site, m.ORIGINAL_CALL); self.mode.publish()
        self.api.put(self.mode.allocation+m.CODE_SIZE+128, bytes(32))
        with self.assertRaises(RuntimeError):
            m.PetOutlineKeeper(self.game, 1, api=self.api).publish()
        with self.assertRaises(ValueError):
            m.PetOutlineKeeper(self.game, 1, api=self.api, code=bytes(m.CODE_SIZE))

    def test_write_failure_is_fatal_and_game_exit_cleanup_is_idempotent(self):
        self.mode.publish(); self.api.failure = "publish"
        with self.assertRaises(OSError):
            self.mode.publish()
        self.mode.publish(); self.api.put(self.extra["meta"], b"\1"); self.api.failure = "publish"
        with self.assertRaises(OSError):
            self.mode.publish()  # Cleanup write failure must not become waiting.
        self.api.running = False; self.mode.close(); self.mode.close()
        self.assertIsNone(self.mode.allocation)

    def test_released_discovery_row_is_not_accepted_or_global_failure(self):
        source = self.extra["nodes"]+8*0x180
        stale = 0x200050000
        put_qword(self.api, source+0xB8, stale)
        put_u32(self.api, source+0x170, 1); self.api.put(source+0x17C, b"\1")
        original_read = self.api.read
        def released_row(address, size):
            if address == stale:
                raise OSError("released unrelated animal")
            return original_read(address, size)
        with patch.object(self.api, "read", side_effect=released_row):
            self.assertEqual(self.mode.publish(), 1)
            self.assertEqual(self.mode.last_binding["dog"], self.extra["dog"])
        def released_pet(address, size):
            if address == self.extra["dog_character"]:
                raise OSError("released pet")
            return original_read(address, size)
        with patch.object(self.api, "read", side_effect=released_pet):
            with self.assertRaises(m.TransientPetState):
                self.mode.publish()
        self.assertEqual(self.api.read(self.mode.allocation+m.CODE_SIZE+72, 8), bytes(8))


class MachineTests(unittest.TestCase):
    def execute(self, *, active=True, condition=None, hidden=1):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
        from unicorn import x86_const as x
        api = FakeAPI(); game, local, extra = fixture(api)
        mode = m.PetOutlineKeeper(game, 1, api=api)
        binding = mode._binding()
        uc = Uc(UC_ARCH_X86, UC_MODE_64)
        uc.mem_map(api.base, 0x3000000); uc.mem_map(api.allocation, m.ALLOCATION_SIZE)
        uc.mem_map(0x200000000, 0x60000); uc.mem_map(0x300000000, 0x10000)
        for address, byte in api.memory.items():
            uc.mem_write(address, bytes([byte]))
        mode.allocation = api.allocation
        mode._publish(binding, 1300 if active else 0)
        uc.mem_write(api.allocation, mode.code)
        uc.mem_write(api.allocation+m.CODE_SIZE, mode._header())
        header = api.allocation+m.CODE_SIZE
        for a in (header+64, header+72, header+256):
            uc.mem_write(a, api.read(a, 8 if a == header+64 else 56 if a == header+72 else 64))
        original, qpc, continuation = api.base+m.ORIGINAL_RVA, api.base+0x1000, api.base+m.CALL_RVA+5
        uc.mem_write(original, b"\xc3"); uc.mem_write(qpc, b"\xc3")
        uc.mem_write(api.base+m.QPC_IAT_RVA, struct.pack("<Q", qpc))
        sp = 0x300008000; uc.mem_write(sp-8, struct.pack("<Q", continuation))
        uc.reg_write(x.UC_X86_REG_RSP, sp-8)
        nonvolatile = {x.UC_X86_REG_RBX: extra["dog"], x.UC_X86_REG_RBP: 0xB0B, x.UC_X86_REG_RSI: 0x5151,
                       x.UC_X86_REG_RDI: 0xD1D, x.UC_X86_REG_R12: 0x1212, x.UC_X86_REG_R13: 0x1313,
                       x.UC_X86_REG_R14: 0x1414, x.UC_X86_REG_R15: 0x1515}
        if condition == "wrong_dog":
            nonvolatile[x.UC_X86_REG_RBX] += 0x100
        for r, value in nonvolatile.items():
            uc.reg_write(r, value)
        uc.reg_write(x.UC_X86_REG_RCX, extra["settings"])
        uc.reg_write(x.UC_X86_REG_RDX, 0xC4)
        for n in range(16):
            uc.reg_write(getattr(x, "UC_X86_REG_XMM"+str(n)), 0x123456789ABC0000+n)
        saved_xmm = {n: uc.reg_read(getattr(x, "UC_X86_REG_XMM"+str(n))) for n in range(6, 16)}
        mutations = {
            "expired": (header+72, struct.pack("<Q", 1000)), "odd": (header+64, struct.pack("<Q", 3)),
            "bad_metadata": (header+256, struct.pack("<Q", 1)),
            "world": (extra["world"]+0x48, bytes(4)),
            "owner": (extra["meta"], b"\1"), "inactive": (extra["meta"]+1, b"\0"),
            "owner_link": (extra["dog"]+0x18, bytes(8)),
            "component_link": (extra["dog_character"]+0x2AD8, bytes(8)),
            "dog_generation": (local["mapping"]+20, struct.pack("<I", (9 << 16)|0x9ABD)),
            "local_generation": (local["mapping"]+12, struct.pack("<I", (7 << 16)|0x1235)),
            "owner_component": (extra["owner_component"]+0x10, bytes(8)),
            "local_rebinding": (extra["local_slot"]+0x170, bytes(8)),
            "dog_type": (extra["dog_source"]+0x170, struct.pack("<I", 2)),
        }
        if condition in mutations:
            uc.mem_write(*mutations[condition])
        if condition == "wrong_setting":
            uc.reg_write(x.UC_X86_REG_RDX, 0x91)
        volatile = (x.UC_X86_REG_RAX, x.UC_X86_REG_RCX, x.UC_X86_REG_RDX,
                    x.UC_X86_REG_R8, x.UC_X86_REG_R9, x.UC_X86_REG_R10, x.UC_X86_REG_R11)
        expected = {r: 0xABC000+r for r in volatile}; expected[x.UC_X86_REG_RAX] = hidden
        return_xmm = {n: 0xFEED0000+n for n in range(6)}
        calls, writes, state = [], [], {}
        def code_hook(cpu, address, size, unused):
            if address == original:
                calls.append("original")
                self.assertEqual(cpu.reg_read(x.UC_X86_REG_RSP) % 16, 8)
                self.assertEqual(cpu.reg_read(x.UC_X86_REG_RCX), extra["settings"])
                self.assertEqual(cpu.reg_read(x.UC_X86_REG_RDX), 0x91 if condition == "wrong_setting" else 0xC4)
                for r, value in expected.items():
                    cpu.reg_write(r, value)
                for n, value in return_xmm.items():
                    cpu.reg_write(getattr(x, "UC_X86_REG_XMM"+str(n)), value)
            elif address == qpc:
                calls.append("qpc")
                self.assertEqual(cpu.reg_read(x.UC_X86_REG_RSP) % 16, 8)
                cpu.mem_write(cpu.reg_read(x.UC_X86_REG_RCX), struct.pack("<Q", 1000))
                for r in volatile:
                    cpu.reg_write(r, 0xDEAD)
                for n in range(6):
                    cpu.reg_write(getattr(x, "UC_X86_REG_XMM"+str(n)), 0xDEAD)
                cpu.reg_write(x.UC_X86_REG_RAX, 0 if condition == "qpc_fail" else 1)
                if condition == "sequence_race":
                    cpu.mem_write(header+64, struct.pack("<Q", 4))
                if condition == "owner_race":
                    cpu.mem_write(extra["meta"], b"\1")
            elif address == continuation:
                state.update(gpr={r: cpu.reg_read(r) for r in volatile},
                             nonvolatile={r: cpu.reg_read(r) for r in nonvolatile},
                             xmm={n: cpu.reg_read(getattr(x, "UC_X86_REG_XMM"+str(n))) for n in range(16)},
                             rsp=cpu.reg_read(x.UC_X86_REG_RSP))
                cpu.emu_stop()
        def write_hook(cpu, access, address, size, value, unused):
            if not 0x300000000 <= address < 0x300010000:
                writes.append((address, size))
        uc.hook_add(UC_HOOK_CODE, code_hook); uc.hook_add(UC_HOOK_MEM_WRITE, write_hook)
        uc.emu_start(api.allocation, continuation+1, count=10000)
        self.assertEqual(state["nonvolatile"], nonvolatile)
        self.assertEqual(state["rsp"], sp)
        self.assertEqual({n: state["xmm"][n] for n in range(6)}, return_xmm)
        self.assertEqual({n: state["xmm"][n] for n in range(6, 16)}, saved_xmm)
        self.assertEqual({r: v for r, v in state["gpr"].items() if r != x.UC_X86_REG_RAX},
                         {r: v for r, v in expected.items() if r != x.UC_X86_REG_RAX})
        self.assertEqual(calls.count("original"), 1)
        self.assertTrue(all(header+320 <= a and a+n <= header+384 for a, n in writes))
        # Private code never writes color, option table, owner state or model.
        self.assertEqual(uc.mem_read(extra["options"]+0x248, 4), struct.pack("<I", 15))
        self.assertEqual(uc.mem_read(extra["options"]+0x310, 4), struct.pack("<I", 1))
        return state["gpr"][x.UC_X86_REG_RAX], struct.unpack("<8Q", uc.mem_read(header+320, 64))

    def test_active_hide_all_zero_and_one_only_override_local_return(self):
        for hidden in (0, 1):
            with self.subTest(hidden=hidden):
                value, stats = self.execute(hidden=hidden)
                self.assertEqual(value, 0); self.assertEqual(stats[1:3], (1, 0))
                self.assertEqual(stats[3:5], (hidden, 0))

    def test_off_expiry_wrong_pet_and_identity_races_default(self):
        self.assertEqual(self.execute(active=False)[0], 1)
        for condition in ("expired", "odd", "bad_metadata", "wrong_dog", "world", "owner", "inactive", "owner_link",
                          "component_link", "dog_generation", "local_generation", "owner_component", "local_rebinding",
                          "dog_type", "wrong_setting", "qpc_fail", "sequence_race", "owner_race"):
            with self.subTest(condition=condition):
                value, stats = self.execute(condition=condition)
                self.assertEqual(value, 1); self.assertEqual(stats[1:3], (0, 1))

    def test_native_outline_off_returns_before_pet_hook(self):
        # Original preamble and branch from supported 6A7E30, not a Python
        # model of the option. DogOutline=0 takes the native epilogue directly.
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
        from unicorn import x86_const as x
        uc = Uc(UC_ARCH_X86, UC_MODE_64); base = 0x140000000
        uc.mem_map(base, 0x3000000); uc.mem_map(0x300000000, 0x10000)
        start, end = base+0x6A7E30, base+0x6A7EFD
        uc.mem_write(start, m.SIGNATURES[0x6A7E30]); uc.mem_write(base+m.ORIGINAL_RVA, b"\xc3")
        uc.reg_write(x.UC_X86_REG_RSP, 0x300008008)
        calls = []
        def observe(cpu, address, size, unused):
            if address == base+m.ORIGINAL_RVA:
                calls.append(cpu.reg_read(x.UC_X86_REG_RDX)); cpu.reg_write(x.UC_X86_REG_RAX, 0)
            if address == end:
                cpu.emu_stop()
            self.assertNotEqual(address, base+m.CALL_RVA)
        uc.hook_add(UC_HOOK_CODE, observe); uc.emu_start(start, end+1, count=100)
        self.assertEqual(calls, [0x91])

    def test_artifact_hash_and_pic_instruction_boundaries(self):
        from capstone import Cs, CS_ARCH_X86, CS_MODE_64
        code = Path(m.__file__).with_name("pet_stub.bin").read_bytes()
        self.assertEqual(len(code), m.CODE_SIZE)
        self.assertEqual(hashlib.sha256(code).hexdigest(), m.STUB_SHA256)
        instructions = list(Cs(CS_ARCH_X86, CS_MODE_64).disasm(code.rstrip(b"\0"), 0))
        self.assertEqual(instructions[0].mnemonic, "sub")
        self.assertEqual(instructions[-1].mnemonic, "ret")


if __name__ == "__main__":
    unittest.main()
