"""Offline CPU tests: execute installed game's actual pure AI attenuation bodies."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
import silencer_ai_mode as m
from test_silencer_support import FIXTURES,hash32,resource_catalog
from test_ninja_mode import FakeAPI as BaseAPI, fixture as local_fixture

NATIVE={int(rva):bytes.fromhex(raw) for rva,raw in FIXTURES['native'].items()}
CONST_RVA=FIXTURES['constant_rva']
CONST_BYTES=bytes.fromhex(FIXTURES['constant'])
assert all(b[-1]==0xC3 for b in NATIVE.values())
PROFILES=FIXTURES['profiles']
WEAPONS=FIXTURES['weapons']


AI_BASE, MANAGER, HOST, HEAD = 0x210000000, 0x210001000, 0x210002000, 0x210003000


class FakeAPI(BaseAPI):
    def __init__(self):
        super().__init__()
        for rva, data in m.SIGNATURES.items():self.put(self.base + rva, data)
        for (rva, _, _), data in zip(m.CALLS, m.ORIGINAL_CALLS):self.put(self.base + rva, data)
        self.freeze_depth = 0

    def write(self, address, data):
        self.events.append(('write', address, len(data)))
        for index, (rva, _, _) in enumerate(m.CALLS):
            if address == self.base + rva and self.failure == ('partial', index):
                self.failure = None
                self.put(address, data[:2])
                raise OSError('partial AI CALL')
        if address == self.allocation + m.CODE_SIZE + 72 and self.failure == 'lease':
            self.failure = None
            self.put(address, data[:4])
            raise OSError('lease write')
        self.put(address, data)

    def flush(self, address, size):
        self.events.append(('flush', address))
        for index, (rva, _, _) in enumerate(m.CALLS):
            if address == self.base + rva and self.failure == ('flush', index):
                self.failure = None
                raise OSError('flush')

    def protect(self, address, size, protection):
        self.events.append(('protect', address, protection))
        for index, (rva, _, _) in enumerate(m.CALLS):
            if address != self.base + rva:continue
            if self.failure == ('protect', index) and protection == 0x40:
                self.failure = None
                raise OSError('protect')
            if self.failure == ('restore_protect', index) and protection == 0x20:
                self.failure = None
                raise OSError('restore protection')
        return 0x20

    @contextmanager
    def frozen_threads(self, site, size):
        index = self.freeze_depth
        self.freeze_depth += 1
        self.events.append(('suspend', site))
        try:
            if self.failure == ('context', index):raise OSError('context')
            yield
        finally:
            self.events.append(('resume', site))
            self.freeze_depth -= 1


def fixture(api):
    game, binding, extra = local_fixture(api)
    game.exe.read_bytes = lambda:b'fake silencer AI game'
    api.put(api.base + 0x27C5D30, struct.pack('<Q', MANAGER))
    api.put(MANAGER + 0x220, struct.pack('<Q', HOST))
    api.put(HOST + 0x368, struct.pack('<6f', *PROFILES['base'][:6]))
    api.put(HOST + 0x388, struct.pack('<Q', HEAD))
    api.put(HEAD + 0x19, b'\x01')
    keys = sorted((hash32(name), values) for name, values in PROFILES.items() if name != 'base')
    nodes = {}
    def build(items):
        if not items:return HEAD
        middle = len(items) // 2
        key, values = items[middle]
        address = AI_BASE + 0x4000 + len(nodes) * 0x80
        nodes[key] = address
        left, right = build(items[:middle]), build(items[middle + 1:])
        api.put(address, struct.pack('<3Q', left, HEAD, right))
        api.put(address + 0x19, b'\x00')
        api.put(address + 0x1C, struct.pack('<I7f', key, *values))
        return address
    root = build(keys)
    api.put(HEAD + 8, struct.pack('<Q', root))
    return game, binding, dict(extra, ai_nodes=nodes, ai_root=root, bow_node=nodes[m.LONG_BOW_HASH])


class NativeHarness:
    def __init__(self, case):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
        from unicorn import x86_const as x
        self.case, self.x = case, x
        self.api = FakeAPI()
        self.game, self.binding, self.extra = fixture(self.api)
        self.mode = m.SilencerAiMode(self.game, 1, api=self.api)
        self.mode.install()
        self.mode.publish()
        self.uc = uc = Uc(UC_ARCH_X86, UC_MODE_64)
        uc.mem_map(self.api.base, 0x3000000)
        uc.mem_map(self.mode.allocation, m.ALLOCATION_SIZE)
        uc.mem_map(0x200000000, 0x40000)
        uc.mem_map(AI_BASE, 0x10000)
        uc.mem_map(0x300000000, 0x10000)
        for address, value in self.api.memory.items():uc.mem_write(address, bytes([value]))
        for rva, body in NATIVE.items():uc.mem_write(self.api.base + rva, body)
        uc.mem_write(self.api.base + CONST_RVA, CONST_BYTES)
        self.header = self.mode.allocation + m.CODE_SIZE
        self.qpc = self.api.base + 0x1000
        uc.mem_write(self.qpc, b'\xc3')
        uc.mem_write(self.api.base + 0x1920518, struct.pack('<Q', self.qpc))
        self.regs = ('RAX', 'RCX', 'RDX', 'R8', 'R9', 'R10', 'R11', 'RBX', 'RBP', 'RSI', 'RDI', 'R12', 'R13', 'R14', 'R15')
        self.condition = None
        self.target = self.stop = 0
        self.target_entries = []
        self.writes = []
        self.qpc_calls = 0
        self.mutations = set()
        uc.hook_add(UC_HOOK_CODE, self.trace)
        uc.hook_add(UC_HOOK_MEM_WRITE, self.watch)

    def snapshot(self):
        x, uc = self.x, self.uc
        return ([uc.reg_read(getattr(x, 'UC_X86_REG_' + name)) for name in self.regs],
                [uc.reg_read(getattr(x, 'UC_X86_REG_XMM' + str(i))) for i in range(16)],
                uc.reg_read(x.UC_X86_REG_EFLAGS), uc.reg_read(x.UC_X86_REG_RSP),
                bytes(uc.mem_read(0x300008000, 64)))

    def watch(self, machine, access, address, size, value, _):
        self.writes.append((machine.reg_read(self.x.UC_X86_REG_RIP), address, size))

    def mutate(self, address, data):
        self.uc.mem_write(address, data)
        self.mutations.update(range(address, address + len(data)))

    def trace(self, machine, address, size, _):
        x, uc, b, e = self.x, self.uc, self.binding, self.extra
        if address == self.stop:
            uc.emu_stop()
        elif address == self.target:
            self.target_entries.append(self.snapshot())
        elif address == self.qpc:
            self.qpc_calls += 1
            self.case.assertEqual(uc.reg_read(x.UC_X86_REG_RSP) % 16, 8)
            uc.mem_write(uc.reg_read(x.UC_X86_REG_RCX), struct.pack('<Q', 1300 if self.condition == 'qpc_expired' else 1000))
            for i, name in enumerate(self.regs[:7]):uc.reg_write(getattr(x, 'UC_X86_REG_' + name), 0xBAD000 + i)
            for i in range(6):uc.reg_write(getattr(x, 'UC_X86_REG_XMM' + str(i)), (0xBAD << 64) + i)
            uc.reg_write(x.UC_X86_REG_EFLAGS, 0x246)
            uc.reg_write(x.UC_X86_REG_RAX, self.condition != 'qpc_fail')
            if self.condition == 'epoch_race':self.mutate(self.header + 64, struct.pack('<Q', 8))
            if self.condition == 'late_local':self.mutate(e['local_slot'] + 0x170, bytes(8))
            if self.condition == 'late_host':self.mutate(MANAGER + 0x220, struct.pack('<Q', HOST + 0x1000))
            if self.condition == 'late_tree':self.mutate(HEAD + 8, struct.pack('<Q', HEAD))
            if self.condition == 'late_player':self.mutate(b['player'] + 0x68, bytes(8))

    def prepare(self, kind, weapon, distance, *, expected_weapon=None):
        x, uc, api = self.x, self.uc, self.api
        self.target = api.base + m.CALLS[kind][2]
        self.stop = self.mode.sites[kind] + 5
        self.target_entries, self.writes, self.qpc_calls, self.mutations = [], [], 0, set()
        uc.reg_write(x.UC_X86_REG_RSP, 0x300008000)
        uc.mem_write(0x300008000, bytes(range(64)))
        uc.mem_write(0x300007FF8, struct.pack('<Q', self.stop))
        for i, name in enumerate(self.regs):uc.reg_write(getattr(x, 'UC_X86_REG_' + name), 0xABC000 + i)
        for name, value in dict(RCX=HOST, R8=weapon if expected_weapon is None else expected_weapon,
                                RBX=self.binding['handle']).items():uc.reg_write(getattr(x, 'UC_X86_REG_' + name), value)
        for i in range(16):uc.reg_write(getattr(x, 'UC_X86_REG_XMM' + str(i)), (0x1234567890 << 64) + i)
        bits = struct.unpack('<I', struct.pack('<f', distance))[0]
        uc.reg_write(x.UC_X86_REG_XMM1, (0x1234567890 << 64) + bits)
        uc.reg_write(x.UC_X86_REG_EFLAGS, 0x202)

    def baseline(self, kind, weapon, distance):
        self.condition = None
        self.prepare(kind, weapon, distance)
        self.uc.reg_write(self.x.UC_X86_REG_RSP, 0x300007FF8)
        before = self.snapshot()
        self.uc.emu_start(self.target, 0, count=1000)
        self.case.assertEqual(len(self.target_entries), 1)
        self.case.assertEqual(self.target_entries[0], before)
        self.case.assertFalse(self.writes)
        return self.snapshot()

    def run(self, kind, weapon, distance, condition=None):
        x, uc, b, e = self.x, self.uc, self.binding, self.extra
        self.condition = condition
        self.prepare(kind, weapon, distance)
        original_entry_rsp = 0x300007FF8
        uc.mem_write(self.header + 64, struct.pack('<Q', 4))
        uc.mem_write(self.header + 72, struct.pack('<Q', 1300))
        if condition == 'off':uc.mem_write(self.header + 72, bytes(8))
        if condition == 'expired':uc.mem_write(self.header + 72, struct.pack('<Q', 1000))
        if condition == 'odd':uc.mem_write(self.header + 64, struct.pack('<Q', 3))
        if condition == 'foreign_source':uc.reg_write(x.UC_X86_REG_RBX, b['handle'] + 1)
        if condition == 'foreign_host':
            foreign_host = AI_BASE + 0xE000
            uc.mem_write(foreign_host + 0x368, struct.pack('<6f', *PROFILES['base'][:6]))
            uc.mem_write(foreign_host + 0x388, struct.pack('<Q', HEAD))
            uc.reg_write(x.UC_X86_REG_RCX, foreign_host)
        if condition == 'missing_ai_manager':uc.mem_write(self.api.base + 0x27C5D30, bytes(8))
        if condition == 'host_changed':uc.mem_write(MANAGER + 0x220, bytes(8))
        if condition == 'local_changed':uc.mem_write(e['local_slot'] + 0x170, bytes(8))
        if condition == 'character_vtable':uc.mem_write(b['character'], bytes(8))
        if condition == 'character_handle':uc.mem_write(b['character'] + 0x2098, struct.pack('<I', b['handle'] + 1))
        if condition == 'player_link':uc.mem_write(b['character'] + 0x2400, bytes(8))
        if condition == 'player_vtable':uc.mem_write(b['player'], bytes(8))
        if condition == 'player_owner':uc.mem_write(b['player'] + 0x68, bytes(8))
        if condition == 'bow_node_flag':uc.mem_write(e['bow_node'] + 0x19, b'\x01')
        if condition == 'bow_node_key':uc.mem_write(e['bow_node'] + 0x1C, struct.pack('<I', 123))
        if condition == 'bow_profile':uc.mem_write(e['bow_node'] + 0x28, struct.pack('<f', 99))
        if condition == 'bow_seventh':uc.mem_write(e['bow_node'] + 0x38, struct.pack('<f', 999))
        if condition == 'bow_unlinked':uc.mem_write(HEAD + 8, struct.pack('<Q', HEAD))
        before = self.snapshot()
        original = bytearray(uc.mem_read(0x200000000, 0x40000))
        ai_original = bytearray(uc.mem_read(AI_BASE, 0x10000))
        uc.emu_start(self.mode.sites[kind], 0, count=7000)
        self.case.assertEqual(len(self.target_entries), 1)
        expected_entry = (list(before[0]), before[1], before[2], original_entry_rsp, before[4])
        if condition is None:expected_entry[0][3] = m.LONG_BOW_HASH
        self.case.assertEqual(self.target_entries[0], expected_entry)
        self.case.assertEqual(uc.reg_read(x.UC_X86_REG_RSP), 0x300008000)
        after = bytearray(uc.mem_read(0x200000000, 0x40000))
        ai_after = bytearray(uc.mem_read(AI_BASE, 0x10000))
        for address in self.mutations:
            if 0x200000000 <= address < 0x200040000:after[address - 0x200000000] = original[address - 0x200000000]
            if AI_BASE <= address < AI_BASE + 0x10000:ai_after[address - AI_BASE] = ai_original[address - AI_BASE]
        self.case.assertEqual(after, original)
        self.case.assertEqual(ai_after, ai_original)
        self.case.assertTrue(all(0x300000000 <= a < 0x300008000 or self.header + 256 <= a < self.header + 312
                                 or pc == self.qpc and a in self.mutations for pc, a, size in self.writes), self.writes)
        return self.snapshot()


class AiModeTests(unittest.TestCase):
    def setUp(self):
        p = patch.object(m.probe, 'EXPECTED_SHA256', hashlib.sha256(b'fake silencer AI game').hexdigest())
        p.start()
        self.addCleanup(p.stop)

    def test_all_137_whitelist_hashes_match_actual_epe_item_ids_and_compiled_table(self):
        catalog = resource_catalog()
        ids = {r['item_id'] for r in catalog['identities'] if any('/' + category + '/' in r['weapon'] for category in
               ('weapon_rifles_01', 'weapon_handguns_01', 'weapon_shotguns_01', 'weapon_bows_01'))}
        self.assertEqual(len(ids), 137)
        self.assertEqual(set(WEAPONS), ids)
        self.assertTrue(all(int(WEAPONS[name], 16) == hash32(name) for name in ids))
        raw = b''.join(struct.pack('<I', int(value, 16)) for value in WEAPONS.values())
        self.assertEqual((ROOT / 'silencer_ai_weapon_hashes.bin').read_bytes(), raw)
        self.assertEqual((ROOT / 'silencer_ai_mode.bin').read_bytes()[4096:4096 + len(raw)], raw)
        self.assertEqual(hash32('equipment_weapon_sa_rifle_ar15_300_01'), 0x426767E2)
        self.assertEqual(hash32('equipment_weapon_compound_bow_60lb_02'), 0x37E0BAF7)

    def test_every_profile_and_distance_matches_actual_native_longbow_body(self):
        h = NativeHarness(self)
        distances = (0., 10., 25., 50., 74.99, 75., 100., 300.)
        for kind in (0, 1):
            expected = {distance:h.baseline(kind, m.LONG_BOW_HASH, distance) for distance in distances}
            for name, value in WEAPONS.items():
                for distance in distances:
                    with self.subTest(kind=kind, weapon=name, distance=distance):
                        self.assertEqual(h.run(kind, int(value, 16), distance), expected[distance])

    def test_off_native_firearm_output_differs_from_on_longbow_and_is_preserved(self):
        for kind in (0, 1):
            h = NativeHarness(self)
            gun = int(WEAPONS['equipment_weapon_sa_rifle_ar15_300_01'], 16)
            distance = 50. if kind == 0 else 10.
            native = h.baseline(kind, gun, distance)
            longbow = h.baseline(kind, m.LONG_BOW_HASH, distance)
            self.assertNotEqual(native[1][0], longbow[1][0])
            self.assertEqual(h.run(kind, gun, distance, 'off'), native)
            self.assertEqual(h.run(kind, gun, distance), longbow)

    def test_unlisted_equipment_hash_keeps_original_native_math_and_arguments(self):
        for kind in (0, 1):
            h = NativeHarness(self)
            unknown = hash32('unlisted_non_weapon_equipment')
            self.assertNotIn(unknown, [int(v, 16) for v in WEAPONS.values()])
            expected = h.baseline(kind, unknown, 50.)
            self.assertEqual(h.run(kind, unknown, 50., 'unlisted'), expected)

    def test_closed_binding_lease_and_profile_changes_preserve_native_arguments(self):
        conditions = ('off', 'expired', 'odd', 'foreign_source', 'foreign_host', 'missing_ai_manager',
                      'host_changed', 'local_changed', 'character_vtable', 'character_handle', 'player_link',
                      'player_vtable', 'player_owner', 'bow_node_flag', 'bow_node_key', 'bow_profile',
                      'bow_seventh', 'bow_unlinked', 'qpc_fail', 'qpc_expired', 'epoch_race',
                      'late_local', 'late_host', 'late_tree', 'late_player')
        for kind in (0, 1):
            for condition in conditions:
                with self.subTest(kind=kind, condition=condition):
                    h = NativeHarness(self)
                    h.run(kind, int(WEAPONS['equipment_weapon_sa_rifle_ar15_300_01'], 16), 50., condition)

    def test_default_off_two_site_publish_reuse_restore_and_other_native_sites_unchanged(self):
        api = FakeAPI()
        game, binding, extra = fixture(api)
        o = m.SilencerAiMode(game, 1, api=api)
        before = dict(api.memory)
        o.install()
        self.assertEqual(api.read(o.allocation + m.CODE_SIZE + 72, 8), bytes(8))
        o.publish()
        self.assertEqual(o._binding()['bow_node'], extra['bow_node'])
        other = m.SilencerAiMode(game, 2, api=api)
        other.install()
        self.assertEqual(other.allocation, o.allocation)
        self.assertEqual(sum(e[0] == 'allocate' for e in api.events), 1)
        other.close()
        self.assertEqual(tuple(api.read(site, 5) for site in o.sites), m.ORIGINAL_CALLS)
        for address, byte in before.items():self.assertEqual(api.memory[address], byte)
        self.assertFalse(any(e[0] == 'free' for e in api.events))

    def test_two_site_install_restore_faults_roll_back_before_any_thread_resume(self):
        for uninstall in (False, True):
            for failure in [('partial', 0), ('partial', 1), ('flush', 0), ('flush', 1), ('context', 0), ('context', 1),
                            ('protect', 0), ('protect', 1), ('restore_protect', 0), ('restore_protect', 1)]:
                with self.subTest(uninstall=uninstall, failure=failure):
                    api = FakeAPI()
                    game, _, _ = fixture(api)
                    o = m.SilencerAiMode(game, 1, api=api)
                    if uninstall:o.install()
                    before = tuple(api.read(site, 5) for site in o.sites)
                    api.failure = failure
                    with self.assertRaises((OSError, RuntimeError)):
                        o.close() if uninstall else o.install()
                    self.assertEqual(tuple(api.read(site, 5) for site in o.sites), before)
                    self.assertEqual(api.freeze_depth, 0)
                    self.assertEqual(sum(e[0] == 'suspend' for e in api.events), sum(e[0] == 'resume' for e in api.events))

    def test_wrong_game_foreign_half_patch_tampered_code_and_failed_lease_refused(self):
        api = FakeAPI()
        game, _, _ = fixture(api)
        o = m.SilencerAiMode(game, 1, api=api)
        game.exe.read_bytes = lambda:b'bad'
        with self.assertRaises(RuntimeError):o.install()
        self.assertFalse(api.events)
        game.exe.read_bytes = lambda:b'fake silencer AI game'
        api.put(o.sites[0], b'\x90' * 5)
        with self.assertRaises(RuntimeError):o.install()
        api.put(o.sites[0], m.ORIGINAL_CALLS[0])
        o.publish()
        api.put(o.sites[1], m.ORIGINAL_CALLS[1])
        with self.assertRaises(RuntimeError):o.publish()
        self.assertEqual(api.read(o.allocation + m.CODE_SIZE + 72, 8), bytes(8))
        api.put(o.sites[1], o._patched(o.allocation)[1])
        api.failure = 'lease'
        with self.assertRaises(OSError):o.publish()
        self.assertEqual(api.read(o.allocation + m.CODE_SIZE + 72, 8), bytes(8))
        api.put(o.allocation + 4096, b'\x90')
        with self.assertRaises(RuntimeError):o.publish()

    def test_python_profile_binding_rejects_unavailable_or_changed_longbow(self):
        for condition in ('manager', 'host', 'head', 'missing', 'different', 'cycle'):
            with self.subTest(condition=condition):
                api = FakeAPI()
                game, _, extra = fixture(api)
                o = m.SilencerAiMode(game, 1, api=api)
                if condition == 'manager':api.put(api.base + 0x27C5D30, bytes(8))
                if condition == 'host':api.put(MANAGER + 0x220, bytes(8))
                if condition == 'head':api.put(HOST + 0x388, bytes(8))
                if condition == 'missing':api.put(HEAD + 8, struct.pack('<Q', HEAD))
                if condition == 'different':api.put(extra['bow_node'] + 0x28, struct.pack('<f', 3))
                if condition == 'cycle':api.put(HEAD + 8, struct.pack('<Q', HOST))
                with self.assertRaises((RuntimeError, OSError)):o.publish()
                self.assertEqual(api.read(o.allocation + m.CODE_SIZE + 72, 8), bytes(8))


if __name__ == '__main__':unittest.main(verbosity=2)
