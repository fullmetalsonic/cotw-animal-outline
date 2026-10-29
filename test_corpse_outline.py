"""Offline fake-API and x64 CPU tests; never attach to a game process."""
from contextlib import contextmanager
from collections import Counter
import ctypes as C
import hashlib
from pathlib import Path
import struct
import types
import unittest
from unittest.mock import patch

import corpse_outline as m


class FakeAPI:
    def __init__(self):
        self.memory = {}; self.events = []; self.failed = None; self.running = True
        self.base, self.allocation = 0x140000000, 0x140900000
        self.frozen = False
        for rva, data in m.SIGNATURES.items():
            self.put(self.base + rva, data)
        self.put(self.base + m.CALL_RVA, m.ORIGINAL_CALL)

    def put(self, address, payload):
        self.memory.update((address+i, b) for i, b in enumerate(payload))

    def read(self, address, size):
        return bytes(self.memory.get(address+i, 0) for i in range(size))

    def write(self, address, payload):
        self.events.append(("write", address, len(payload), self.frozen))
        if not self.running:
            raise OSError("process exited")
        if address == self.allocation+m.CODE_SIZE+72 and self.failed == "publish_payload":
            self.failed = None; self.put(address, payload[:8]); raise OSError("partial publish")
        if address == self.base + m.CALL_RVA and payload != m.ORIGINAL_CALL and self.failed == "partial_patch":
            self.failed = None; self.put(address, payload[:2]); raise OSError("partial patch")
        self.put(address, payload)

    def allocate_near(self, site):
        self.events.append(("allocate",)); return self.allocation

    def protect(self, address, size, protection):
        self.events.append(("protect", address, size, protection)); return 0x20

    def flush(self, address, size):
        self.events.append(("flush", address, size))
        if address == self.base + m.CALL_RVA and self.failed == "flush":
            self.failed = None; raise OSError("cache flush")

    def clock(self):
        return 1000, 1000

    def is_running(self):
        return self.running

    @contextmanager
    def frozen_threads(self, site, length):
        self.events.append(("suspend",)); self.frozen = True
        try:
            if self.failed == "context":
                raise OSError("context verification")
            yield
        finally:
            self.frozen = False; self.events.append(("resume",))


def make_game(api):
    game = types.SimpleNamespace(base=api.base, pid=123,
                                 exe=types.SimpleNamespace(read_bytes=lambda: b"fake game"))
    return game


def add_corpse(api, index=0):
    wrapper, character, definition, path_pointer = (0x200000000 + index*0x10000 + n for n in (0, 0x2000, 0x6000, 0x7000))
    path = "animations/hp_ragdoll/birds/wild_turkey/test.ragdoll"
    raw = bytearray(0x260)
    struct.pack_into("<Q", raw, 0, character)
    struct.pack_into("<Q", raw, 0x28, definition)
    struct.pack_into("<I", raw, 0xCC, 270)
    raw[0xD4] = 0x9E
    api.put(wrapper, raw)
    api.put(character, struct.pack("<Q", api.base+m.VTABLE_RVA))
    api.put(character+0x21C, b"\x01")
    api.put(character+0x1098, struct.pack("<I", 1))
    api.put(definition+0xC0, struct.pack("<Q", path_pointer))
    api.put(path_pointer, path.encode()+b"\0")
    return dict(wrapper=hex(wrapper), character=hex(character), definition=hex(definition),
                state_cc=270, vtable_rva=hex(m.VTABLE_RVA), definition_path_c0=path)


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeAPI(); self.game = make_game(self.api)
        self.hash_patch = patch.object(m.probe, "EXPECTED_SHA256", hashlib.sha256(b"fake game").hexdigest())
        self.hash_patch.start(); self.addCleanup(self.hash_patch.stop)
        self.renderer = m.CorpseRenderer(self.game, 1, api=self.api)
        self.row = add_corpse(self.api)

    def test_install_publish_disable_reuse(self):
        self.assertEqual(self.renderer.publish([self.row], (1, .35, 0)), 1)
        site = self.game.base+m.CALL_RVA; header = self.api.allocation+m.CODE_SIZE
        self.assertEqual(self.api.read(site, 5), m.rel_call(site, self.api.allocation))
        self.assertEqual(struct.unpack("<QQ", self.api.read(header+72, 16)), (1300, 1))
        self.assertEqual(struct.unpack("<4f", self.api.read(header+88, 16))[-1], 1)
        self.assertTrue(all(event[3] for event in self.api.events if event[0] == "write" and event[1] == site))
        self.renderer.disable(); self.renderer.close()
        self.assertEqual(self.api.read(header+72, 16), bytes(16))
        allocation_count = sum(e[0] == "allocate" for e in self.api.events)
        second = m.CorpseRenderer(self.game, 1, api=self.api)
        self.assertEqual(second.publish([self.row], (0, .55, 1)), 1)
        self.assertEqual(allocation_count, sum(e[0] == "allocate" for e in self.api.events))
        self.assertFalse(any(e[0] == "free" for e in self.api.events))

    def test_partial_write_and_flush_failure_roll_back_before_resume(self):
        for failure in ("partial_patch", "flush", "context"):
            with self.subTest(failure=failure):
                api = FakeAPI(); api.failed = failure
                renderer = m.CorpseRenderer(make_game(api), 1, api=api)
                with self.assertRaises((OSError, RuntimeError)):
                    renderer.publish([add_corpse(api)], (1, 1, 1))
                self.assertEqual(api.read(api.base+m.CALL_RVA, 5), m.ORIGINAL_CALL)
                self.assertEqual(api.events[-1], ("resume",))

    def test_foreign_patch_and_owned_code_tamper_rejected(self):
        self.api.put(self.renderer.site, b"\x90"*5)
        with self.assertRaises(RuntimeError):
            self.renderer.publish([self.row])
        self.assertFalse(any(e[0] == "allocate" for e in self.api.events))
        self.api.put(self.renderer.site, m.ORIGINAL_CALL)
        self.renderer.publish([self.row])
        self.api.put(self.api.allocation+100, b"X")
        other = m.CorpseRenderer(self.game, 1, api=self.api)
        with self.assertRaises(RuntimeError):
            other.publish([self.row])

    def test_alive_stale_dog_rows_are_never_published(self):
        self.api.put(int(self.row["wrapper"], 16)+0x17C, struct.pack("<f", 1))
        self.assertEqual(self.renderer.publish([self.row]), 0)
        self.assertFalse(any(e[0] == "allocate" for e in self.api.events))
        self.api.put(int(self.row["wrapper"], 16)+0x17C, bytes(4))
        stale = dict(self.row, state_cc=271)
        dog = dict(self.row, definition_path_c0="animations/hp_ragdoll/animals/labrador/test.ragdoll")
        self.assertEqual(self.renderer.publish([stale, dog]), 0)

    def test_bad_color_and_binary_fail_before_install(self):
        for color in ((1, 2, 0), (float("nan"), 0, 0), (1, 0)):
            with self.assertRaises(ValueError):
                self.renderer.publish([self.row], color)
        with self.assertRaises(ValueError):
            m.CorpseRenderer(self.game, 1, api=self.api, code=bytes(m.CODE_SIZE))
        self.assertFalse(self.api.events)

    def test_rejected_new_version_signature_never_patches(self):
        self.api.put(self.game.base+m.UPDATE_RVA, b"X")
        with self.assertRaises(RuntimeError):
            self.renderer.publish([self.row])
        self.assertFalse(self.api.events)

    def test_partial_publish_disables_and_closed_process_cleanup_is_safe(self):
        self.renderer.publish([self.row])
        self.api.failed = "publish_payload"
        with self.assertRaises(OSError):
            self.renderer.publish([self.row])
        header = self.api.allocation+m.CODE_SIZE
        self.assertEqual(struct.unpack("<Q", self.api.read(header+64, 8))[0] & 1, 1)
        self.assertEqual(self.api.read(header+72, 16), bytes(16))
        self.api.running = False
        self.renderer.close(); self.renderer.close()
        self.assertIsNone(self.renderer.allocation)


class ThreadSafetyTests(unittest.TestCase):
    def test_native_write_requires_full_count_and_matching_postimage(self):
        native = m.NativeAPI.__new__(m.NativeAPI)
        native.writer = 1
        class K:
            count = 4
            def WriteProcessMemory(self, handle, address, buffer, size, count):
                C.cast(count, C.POINTER(C.c_size_t)).contents.value = self.count
                return True
        native.k = K()
        native.read = lambda address, size: b"FAIL"
        with self.assertRaises(OSError):
            native.write(0x10000, b"TEST")
        native.read = lambda address, size: b"TEST"
        native.k.count = 2
        with self.assertRaises(OSError):
            native.write(0x10000, b"TEST")
        native.k.count = 4
        native.write(0x10000, b"TEST")

    def make_native(self, *, failure=None):
        native = m.NativeAPI.__new__(m.NativeAPI)
        native.game = types.SimpleNamespace(pid=123)
        events = []
        class K:
            def OpenThread(self, rights, inherit, tid):
                return tid
            def GetProcessIdOfThread(self, tid):
                return 123
            def SuspendThread(self, tid):
                events.append(("suspend", tid))
                return 0xFFFFFFFF if failure == "suspend" and tid == 2 else 0
            def ResumeThread(self, tid):
                events.append(("resume", tid)); return 1
            def CloseHandle(self, tid):
                events.append(("close", tid))
            def GetThreadContext(self, tid, pointer):
                C.c_uint64.from_address(pointer.value+248).value = 100 if failure == "rip" else 200
                return failure != "context"
        native.k = K()
        snapshots = iter([{1, 2}, {1, 2, 3}] if failure == "enumeration" else [{1, 2}]*3)
        native._thread_ids = lambda: next(snapshots)
        return native, events

    def test_every_suspended_thread_resumes_on_all_guard_failures(self):
        for failure in ("suspend", "context", "rip", "enumeration"):
            with self.subTest(failure=failure):
                native, events = self.make_native(failure=failure)
                with self.assertRaises(OSError):
                    with native.frozen_threads(100, 5):
                        self.fail("unsafe yield")
                suspended = [tid for action, tid in events if action == "suspend" and not (failure == "suspend" and tid == 2)]
                resumed = [tid for action, tid in events if action == "resume"]
                self.assertEqual(sorted(suspended), sorted(resumed))

    def test_success_and_body_exception_resume_all_threads(self):
        native, events = self.make_native()
        with self.assertRaisesRegex(RuntimeError, "body"):
            with native.frozen_threads(100, 5):
                raise RuntimeError("body")
        self.assertEqual([e for e in events if e[0] == "resume"], [("resume", 2), ("resume", 1)])


class MachineCodeTests(unittest.TestCase):
    """Execute the real assembled stub with fake engine/QPC callbacks."""
    def run_stub(self, *, expired=False, mismatch=False, changed_sequence=False, count=1, guard=None):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
        from unicorn import x86_const as x
        uc = Uc(UC_ARCH_X86, UC_MODE_64)
        game, alloc, objects, stack = 0x140000000, 0x150000000, 0x200000000, 0x300000000
        uc.mem_map(game, 0x3000000); uc.mem_map(alloc, m.ALLOCATION_SIZE)
        uc.mem_map(objects, 0x10000); uc.mem_map(stack, 0x10000)
        api = FakeAPI(); api.base = game; row = add_corpse(api)
        for address, value in api.memory.items():
            uc.mem_write(address, bytes([value]))
        renderer = m.CorpseRenderer(make_game(api), 1, api=api)
        uc.mem_write(alloc, renderer.code); uc.mem_write(alloc+m.CODE_SIZE, renderer._header())
        header = alloc+m.CODE_SIZE
        uc.mem_write(header+64, struct.pack("<3Q", 2, 500 if expired else 1300, 1))
        uc.mem_write(header+88, m.color_rgba((1, .35, 0)))
        packed = renderer._row(row)
        if mismatch:
            packed = struct.pack("<Q", objects+8)+packed[8:]
        uc.mem_write(header+256, packed)
        char = int(row["character"], 16)
        uc.mem_write(char+0x1098, struct.pack("<I", count))
        model = objects+0x8000
        uc.mem_write(char+0x11A0, struct.pack("<Q", model))
        uc.mem_write(model+0xC, struct.pack("<I", 0x40))
        qpc_address, return_address = game+0x1000, game+0x2000
        uc.mem_write(game+m.QPC_IAT_RVA, struct.pack("<Q", qpc_address))
        for address in (qpc_address, game+m.UPDATE_RVA, game+m.RESET_RVA):
            uc.mem_write(address, b"\xc3")
        uc.mem_write(game+m.EPILOGUE_RVA, bytes.fromhex("488b9c24e80000004881c4c00000005fc3"))
        caller_sp = stack+0x8000
        uc.mem_write(caller_sp-8, struct.pack("<Q", game+m.CALL_RVA+5))
        uc.mem_write(caller_sp+0xC8, struct.pack("<Q", return_address))
        originals = {x.UC_X86_REG_RBX: 0xBBBB, x.UC_X86_REG_RSI: 0x5151,
                     x.UC_X86_REG_RBP: 0xB0B0, x.UC_X86_REG_RDI: 0xD1D1}
        for offset, reg in ((0xE8, x.UC_X86_REG_RBX), (0xE0, x.UC_X86_REG_RSI),
                            (0xD8, x.UC_X86_REG_RBP), (0xC0, x.UC_X86_REG_RDI)):
            uc.mem_write(caller_sp+offset, struct.pack("<Q", originals[reg]))
        uc.mem_write(caller_sp+0x90, bytes.fromhex("88"*16))
        uc.mem_write(caller_sp+0xA0, bytes.fromhex("77"*16))
        uc.reg_write(x.UC_X86_REG_RBX, objects)
        uc.reg_write(x.UC_X86_REG_RCX, char)
        uc.reg_write(x.UC_X86_REG_RSP, caller_sp-8)
        invalid = {
            "alive": (objects+0x17C, struct.pack("<f", 1)),
            "nan_health": (objects+0x17C, struct.pack("<f", float("nan"))),
            "render_flag": (objects+0xD4, b"\0"),
            "released": (objects+0xCC, struct.pack("<I", 0xDEADBEEF)),
            "vtable": (char, bytes(8)),
            "character": (objects, struct.pack("<Q", char+8)),
            "definition": (objects+0x28, struct.pack("<Q", objects+0x6008)),
            "odd_sequence": (header+64, struct.pack("<Q", 3)),
            "zero_deadline": (header+72, bytes(8)),
            "zero_rows": (header+80, bytes(8)),
            "too_many_rows": (header+80, struct.pack("<Q", 4097)),
            "not_dead": (char+0x21C, b"\0"),
            "processed": (objects+0x25C, b"\x01"),
        }
        if guard in invalid:
            uc.mem_write(*invalid[guard])
        for reg in (x.UC_X86_REG_RAX, x.UC_X86_REG_RDX, x.UC_X86_REG_R8,
                    x.UC_X86_REG_R9, x.UC_X86_REG_R10, x.UC_X86_REG_R11):
            uc.reg_write(reg, reg+100)
        volatile = {reg: uc.reg_read(reg) for reg in (x.UC_X86_REG_RAX, x.UC_X86_REG_RCX,
                    x.UC_X86_REG_RDX, x.UC_X86_REG_R8, x.UC_X86_REG_R9, x.UC_X86_REG_R10, x.UC_X86_REG_R11)}
        for n in range(6):
            uc.reg_write(getattr(x, "UC_X86_REG_XMM"+str(n)), n+1000)
        events, writes = [], []
        def on_code(cpu, address, size, unused):
            if address == qpc_address:
                self.assertEqual(cpu.reg_read(x.UC_X86_REG_RSP) % 16, 8)
                cpu.mem_write(cpu.reg_read(x.UC_X86_REG_RCX), struct.pack("<Q", 1000))
                for reg in volatile:
                    cpu.reg_write(reg, 0xFEFE)
                for n in range(6):
                    cpu.reg_write(getattr(x, "UC_X86_REG_XMM"+str(n)), 0xFEFE)
                cpu.reg_write(x.UC_X86_REG_RAX, 0 if guard == "qpc_failure" else 1)
                if changed_sequence:
                    cpu.mem_write(header+64, struct.pack("<Q", 4))
            elif address == game+m.RESET_RVA:
                events.append("reset")
                for reg, value in volatile.items():
                    self.assertEqual(cpu.reg_read(reg), value)
                for n in range(6):
                    self.assertEqual(cpu.reg_read(getattr(x, "UC_X86_REG_XMM"+str(n))), n+1000)
            elif address == game+m.UPDATE_RVA:
                events.append("update")
                self.assertEqual(cpu.reg_read(x.UC_X86_REG_RCX), char)
                self.assertEqual(cpu.reg_read(x.UC_X86_REG_XMM1), 0)
                self.assertEqual(cpu.reg_read(x.UC_X86_REG_RSP) % 16, 8)
                # The engine boundary is intentionally mocked; no claim that
                # CPU emulation proves the game's actual render result.
                cpu.mem_write(model+0xC, struct.pack("<I", (1 << 22)))
            elif address in (return_address, game+m.CALL_RVA+5):
                events.append("active_return" if address == return_address else "default_return")
                cpu.emu_stop()
        def on_write(cpu, access, address, size, value, unused):
            if not stack <= address < stack+0x10000:
                writes.append((address, size))
        uc.hook_add(UC_HOOK_CODE, on_code); uc.hook_add(UC_HOOK_MEM_WRITE, on_write)
        uc.emu_start(alloc, alloc+4096, count=10000)
        self.assertIn(events[-1], ("active_return", "default_return"))
        return uc, events, writes, originals, char, model, caller_sp

    def test_active_abi_epilogue_and_exact_write_ranges(self):
        from unicorn import x86_const as x
        uc, events, writes, originals, char, model, sp = self.run_stub()
        self.assertEqual(events, ["update", "active_return"])
        self.assertEqual(uc.reg_read(x.UC_X86_REG_RSP), sp+0xD0)
        for reg, value in originals.items():
            self.assertEqual(uc.reg_read(reg), value)
        self.assertEqual(uc.reg_read(x.UC_X86_REG_XMM8), int.from_bytes(bytes.fromhex("88"*16), "little"))
        self.assertEqual(uc.reg_read(x.UC_X86_REG_XMM7), int.from_bytes(bytes.fromhex("77"*16), "little"))
        # Unicorn reports MOVUPS as two 8-byte events. Compare every touched
        # byte and its write count, retaining the exact range boundary check.
        expected = [(char+0x2458, 16), (char+0x2468, 16),
                    (char+0x2478, 4), (char+0x247C, 4), (char+0x2480, 4), (model+0xC, 4)]
        self.assertEqual(Counter(a+i for a, n in writes for i in range(n)),
                         Counter(a+i for a, n in expected for i in range(n)))
        self.assertEqual(struct.unpack("<4f", uc.mem_read(char+0x2458, 16))[3], 1)

    def test_expired_changed_sequence_identity_and_model_bounds_default(self):
        for kwargs in ({"expired": True}, {"changed_sequence": True}, {"mismatch": True}, {"count": 65}, {"count": 0}):
            with self.subTest(kwargs=kwargs):
                uc, events, writes, originals, char, model, sp = self.run_stub(**kwargs)
                self.assertEqual(events, ["reset", "default_return"])
                self.assertEqual(writes, [])

    def test_native_object_lease_and_qpc_guards_default_without_object_writes(self):
        for guard in ("alive", "nan_health", "render_flag", "released", "vtable", "character", "definition",
                      "odd_sequence", "zero_deadline", "zero_rows", "too_many_rows", "not_dead", "processed", "qpc_failure"):
            with self.subTest(guard=guard):
                _, events, writes, *_ = self.run_stub(guard=guard)
                self.assertEqual(events, ["reset", "default_return"])
                self.assertEqual(writes, [])

    def test_code_hash_and_static_instruction_boundaries(self):
        from capstone import Cs, CS_ARCH_X86, CS_MODE_64
        code = Path(m.__file__).with_name("corpse_stub.bin").read_bytes()
        self.assertEqual(len(code), m.CODE_SIZE)
        self.assertEqual(hashlib.sha256(code).hexdigest(), m.STUB_SHA256)
        instructions = list(Cs(CS_ARCH_X86, CS_MODE_64).disasm(code.rstrip(b"\0"), 0))
        self.assertEqual(instructions[0].mnemonic, "sub")
        self.assertTrue(any(i.mnemonic == "call" and "[rip" in i.op_str for i in instructions))


if __name__ == "__main__":
    unittest.main()
