"""Game-free tests of real assembled private audio replacement instructions."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import types
import unittest
import uuid
from unittest.mock import patch

from test_silencer_support import resource_catalog
import silencer_audio_mode as m
from test_ninja_mode import FakeAPI as BaseAPI


class FakeAPI(BaseAPI):
    def __init__(self):
        super().__init__()
        for rva, raw in m.SIGNATURES.items():self.put(self.base + rva, raw)
        self.put(self.base + m.CALL_RVA, m.ORIGINAL_CALL)

    def write(self, address, data):
        self.events.append(('write', address, len(data)))
        if address == self.base + m.CALL_RVA and self.failure == 'audio_partial':
            self.failure = None
            self.put(address, data[:2])
            raise OSError('partial audio patch')
        if address == self.allocation + m.CODE_SIZE + 72 and self.failure == 'lease_partial':
            self.failure = None
            self.put(address, data[:4])
            raise OSError('partial lease')
        self.put(address, data)

    def flush(self, address, size):
        self.events.append(('flush', address))
        if address == self.base + m.CALL_RVA and self.failure == 'audio_flush':
            self.failure = None
            raise OSError('audio flush')


def fixture(api):
    return types.SimpleNamespace(base=api.base, pid=123, exe=types.SimpleNamespace(read_bytes=lambda: b'fake audio mode game'))


class AudioModeTests(unittest.TestCase):
    def setUp(self):
        p = patch.object(m.probe, 'EXPECTED_SHA256', hashlib.sha256(b'fake audio mode game').hexdigest())
        p.start()
        self.addCleanup(p.stop)

    def test_mapping_longbow_fire_pure_bow_impacts_and_compiled_table_agree(self):
        o = m.SilencerAudioMode(fixture(FakeAPI()), 1, api=FakeAPI())
        self.assertEqual(len(o.mapping), 85)
        self.assertEqual(sum(kind == 1 for _, _, kind in o.mapping), 73)
        self.assertEqual(sum(kind == 2 for _, _, kind in o.mapping), 12)
        mapping = json.loads((m.ROOT / 'silencer-audio-mode-map.json').read_text(encoding='utf8'))
        self.assertEqual(mapping['targetlabel_longbow'], 'equipment_weapon_longbow_01')
        self.assertEqual(mapping['bow_fire'], 'e82ceeac-b413-4e5a-a5c6-f588fcba43f8')
        self.assertEqual(mapping['impact']['5a6b771d-3754-43fa-a7b0-aad053b391e0'], 'f474fe02-9222-43be-8bfa-1f8667859ab9')
        self.assertEqual(mapping['impact_policy']['longbow_table_agreement'], '49 of 50 GUID material fields')
        self.assertTrue(all(source != target for source, target, _ in o.mapping))

    def test_default_off_publish_reuse_disable_restore_and_other_sites_unchanged(self):
        api = FakeAPI()
        other_sites = {a:b for a,b in api.memory.items() if a < api.allocation and not api.base + m.CALL_RVA <= a < api.base + m.CALL_RVA + 5}
        o = m.SilencerAudioMode(fixture(api), 1, api=api)
        self.assertEqual(o.stats(), {})
        o.install()
        self.assertEqual(api.read(o.allocation + m.CODE_SIZE + 72, 8), bytes(8))
        self.assertEqual(o.publish(), 1)
        self.assertEqual(struct.unpack('<Q', api.read(o.allocation + m.CODE_SIZE + 72, 8))[0], 1300)
        other = m.SilencerAudioMode(fixture(api), 2, api=api)
        other.install()
        self.assertEqual(other.allocation, o.allocation)
        self.assertEqual(sum(e[0] == 'allocate' for e in api.events), 1)
        other.close()
        other.close()
        self.assertEqual(api.read(o.site, 5), m.ORIGINAL_CALL)
        self.assertEqual({a:api.memory[a] for a in other_sites}, other_sites)
        self.assertEqual(sum(e[0] == 'suspend' for e in api.events), sum(e[0] == 'resume' for e in api.events))
        self.assertFalse(any(e[0] == 'free' for e in api.events))

    def test_partial_patch_flush_and_thread_context_rollback_before_resume(self):
        for uninstall in (False, True):
            for failure in ('audio_partial', 'audio_flush', 'context'):
                with self.subTest(uninstall=uninstall, failure=failure):
                    api = FakeAPI()
                    o = m.SilencerAudioMode(fixture(api), 1, api=api)
                    if uninstall:o.install()
                    before = api.read(o.site, 5)
                    api.failure = failure
                    with self.assertRaises((OSError, RuntimeError)):
                        o.close() if uninstall else o.install()
                    self.assertEqual(api.read(o.site, 5), before)
                    self.assertEqual(api.events[-1], ('resume',))

    def test_tamper_foreign_and_wrong_game_refused_and_failed_publish_expires(self):
        api = FakeAPI()
        o = m.SilencerAudioMode(fixture(api), 1, api=api)
        o.game.exe.read_bytes = lambda:b'bad'
        with self.assertRaises(RuntimeError):o.install()
        self.assertFalse(api.events)
        o.game.exe.read_bytes = lambda:b'fake audio mode game'
        api.put(o.site, b'\x90' * 5)
        with self.assertRaises(RuntimeError):o.install()
        self.assertFalse(api.events)
        api.put(o.site, m.ORIGINAL_CALL)
        o.publish()
        api.put(o.allocation + m.CODE_SIZE + 160, bytes(8))
        with self.assertRaises(RuntimeError):o.publish()
        self.assertEqual(api.read(o.allocation + m.CODE_SIZE + 72, 8), bytes(8))
        api.put(o.allocation + m.CODE_SIZE + 160, o._header()[160:168])
        api.failure = 'lease_partial'
        with self.assertRaises(OSError):o.publish()
        self.assertEqual(api.read(o.allocation + m.CODE_SIZE + 72, 8), bytes(8))
        api.put(o.allocation + m.MAP_OFFSET, b'\x90')
        with self.assertRaises(RuntimeError):o.publish()

    def execute(self, entry=None, condition=None, source_guid=None):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
        from unicorn import x86_const as x
        api = FakeAPI()
        o = m.SilencerAudioMode(fixture(api), 1, api=api)
        source, target, kind = entry or o.mapping[0]
        if source_guid is not None:source = source_guid
        o.install()
        if condition != 'off':o.publish()
        uc = Uc(UC_ARCH_X86, UC_MODE_64)
        uc.mem_map(api.base, 0x3000000)
        uc.mem_map(o.allocation, m.ALLOCATION_SIZE)
        uc.mem_map(0x200000000, 0x10000)
        uc.mem_map(0x300000000, 0x10000)
        for address, value in api.memory.items():uc.mem_write(address, bytes([value]))
        wrapper, meta, manager, output = (0x200001000, 0x200002000, 0x200003000, 0x200004000)
        source_desc, studio, target_desc = 0x238C00, 0x20400, 0x345600
        uc.mem_write(wrapper + 0x18, struct.pack('<Q', meta))
        uc.mem_write(meta, struct.pack('<Q', source_desc))
        uc.mem_write(meta + 0x18, uuid.UUID(source).bytes_le)
        uc.mem_write(manager, struct.pack('<Q', api.base + m.MANAGER_VTABLE_RVA))
        uc.mem_write(manager + 0x28, struct.pack('<Q', studio))
        uc.mem_write(api.base + m.MANAGER_RVA, struct.pack('<Q', manager))
        # A source-adjacent sentinel stands for ballistics/ammo data: no writes allowed.
        uc.mem_write(0x200005000, bytes(range(256)))
        header = o.allocation + m.CODE_SIZE
        qpc = api.base + 0x1000
        uc.mem_write(qpc, b'\xc3')
        uc.mem_write(api.base + m.QPC_IAT_RVA, struct.pack('<Q', qpc))
        uc.mem_write(api.base + m.LOOKUP_RVA, b'\xc3')
        uc.mem_write(api.base + m.ORIGINAL_RVA, b'\xc3')
        if condition == 'expired':uc.mem_write(header + 72, struct.pack('<Q', 1000))
        if condition == 'odd':uc.mem_write(header + 64, struct.pack('<Q', 3))
        if condition == 'busy':uc.mem_write(header + 88, struct.pack('<Q', 1))
        if condition == 'missing_manager':uc.mem_write(api.base + m.MANAGER_RVA, bytes(8))
        if condition == 'bad_manager_low':uc.mem_write(api.base + m.MANAGER_RVA, struct.pack('<Q', 0xFFFF))
        if condition == 'bad_manager_high':uc.mem_write(api.base + m.MANAGER_RVA, struct.pack('<Q', 0x800000000000))
        if condition == 'wrong_vtable':uc.mem_write(manager, bytes(8))
        if condition == 'missing_studio':uc.mem_write(manager + 0x28, bytes(8))
        if condition == 'mismatched_metadata':uc.mem_write(meta, struct.pack('<Q', source_desc + 1))
        if condition == 'missing_metadata':uc.mem_write(wrapper + 0x18, bytes(8))
        immutable = bytes(uc.mem_read(0x200000000, 0x10000))
        volatile = ('RAX', 'RCX', 'RDX', 'R8', 'R9', 'R10', 'R11')
        regs = volatile + ('RBX', 'RBP', 'RSI', 'RDI', 'R12', 'R13', 'R14', 'R15')
        calls, lookups, returns, writes, qpcs = [], [], [], [], []

        def snapshot():
            return ([uc.reg_read(getattr(x, 'UC_X86_REG_' + n)) for n in regs],
                    [uc.reg_read(getattr(x, 'UC_X86_REG_XMM' + str(i))) for i in range(16)],
                    uc.reg_read(x.UC_X86_REG_EFLAGS))

        def clobber(seed):
            for i, n in enumerate(volatile):uc.reg_write(getattr(x, 'UC_X86_REG_' + n), seed + i)
            for i in range(6):uc.reg_write(getattr(x, 'UC_X86_REG_XMM' + str(i)), (seed << 64) + i)
            uc.reg_write(x.UC_X86_REG_EFLAGS, 0x246)

        should_swap = source_guid is None and condition in (None, 'create_failure')
        def trace(machine, address, size, _):
            if address == o.site + 5:
                uc.emu_stop()
            elif address == qpc:
                self.assertEqual(uc.reg_read(x.UC_X86_REG_RSP) % 16, 8)
                qpcs.append(address)
                late = len(qpcs) == 2
                uc.mem_write(uc.reg_read(x.UC_X86_REG_RCX), struct.pack('<Q', 1300 if late and condition == 'late_expiry' else 1000))
                clobber(0xBAD)
                uc.reg_write(x.UC_X86_REG_RAX, not (condition == 'qpc_fail' or late and condition == 'late_qpc_fail'))
                if condition == 'epoch_race' or late and condition == 'late_epoch_race':uc.mem_write(header + 64, struct.pack('<Q', 8))
            elif address == api.base + m.LOOKUP_RVA:
                self.assertEqual(uc.reg_read(x.UC_X86_REG_RSP) % 16, 8)
                self.assertEqual(uc.reg_read(x.UC_X86_REG_RCX), studio)
                self.assertEqual(bytes(uc.mem_read(uc.reg_read(x.UC_X86_REG_RDX), 16)), uuid.UUID(target).bytes_le)
                out = uc.reg_read(x.UC_X86_REG_R8)
                self.assertEqual(bytes(uc.mem_read(out, 8)), bytes(8))
                uc.mem_write(out, struct.pack('<Q', 0 if condition == 'lookup_empty' else target_desc))
                lookups.append(address)
                clobber(0xDEAD)
                uc.reg_write(x.UC_X86_REG_RAX, 13 if condition == 'lookup_fail' else 0)
                if condition == 'changed_manager':uc.mem_write(api.base + m.MANAGER_RVA, bytes(8))
                if condition == 'changed_studio':uc.mem_write(manager + 0x28, struct.pack('<Q', studio + 1))
            elif address == api.base + m.ORIGINAL_RVA:
                self.assertEqual(uc.reg_read(x.UC_X86_REG_RSP) % 16, 8)
                actual = snapshot()
                expected = (list(before[0]), before[1], before[2])
                expected[0][1] = target_desc if should_swap else source_desc
                self.assertEqual(actual, expected)
                calls.append(address)
                uc.mem_write(output, struct.pack('<Q', 0x567800))
                clobber(0xBEEF)
                uc.reg_write(x.UC_X86_REG_RAX, 37 if condition == 'create_failure' else 0)
                returns.append(snapshot())
        uc.hook_add(UC_HOOK_CODE, trace)
        uc.hook_add(UC_HOOK_MEM_WRITE, lambda machine, access, address, size, value, _:writes.append((machine.reg_read(x.UC_X86_REG_RIP), address, size)))
        uc.reg_write(x.UC_X86_REG_RSP, 0x300008000)
        uc.mem_write(0x300008000, bytes(range(64)))
        original_stack = bytes(uc.mem_read(0x300008000, 64))
        for i, n in enumerate(regs):uc.reg_write(getattr(x, 'UC_X86_REG_' + n), 0xABC000 + i)
        for n, v in dict(RAX=0xABCDEF00, RCX=source_desc, RDX=output, R8=0x12345678, R9=0x87654321,
                         RDI=0 if condition == 'missing_wrapper' else wrapper).items():uc.reg_write(getattr(x, 'UC_X86_REG_' + n), v)
        for i in range(16):uc.reg_write(getattr(x, 'UC_X86_REG_XMM' + str(i)), (0x1234567890 << 64) + i)
        uc.reg_write(x.UC_X86_REG_EFLAGS, 0x202)
        before = snapshot()
        uc.emu_start(o.site, 0, count=7000)
        self.assertEqual(len(calls), 1)
        self.assertEqual(snapshot(), returns[0])
        self.assertEqual(uc.reg_read(x.UC_X86_REG_RSP), 0x300008000)
        self.assertEqual(bytes(uc.mem_read(0x300008000, 64)), original_stack)
        after = bytearray(uc.mem_read(0x200000000, 0x10000))
        after[output - 0x200000000:output - 0x200000000 + 8] = immutable[output - 0x200000000:output - 0x200000000 + 8]
        if condition == 'changed_studio':after[manager - 0x200000000 + 0x28:manager - 0x200000000 + 0x30] = struct.pack('<Q', studio)
        self.assertEqual(bytes(after), immutable)
        self.assertTrue(all(0x300000000 <= a < 0x300008000
                            or header <= a < header + m.HEADER_SIZE
                            or pc == api.base + m.ORIGINAL_RVA and a == output
                            or pc == api.base + m.LOOKUP_RVA and a in (api.base + m.MANAGER_RVA, manager + 0x28)
                            for pc, a, n in writes), writes)
        self.assertEqual(struct.unpack('<Q', uc.mem_read(header + 88, 8))[0], 1 if condition == 'busy' else 0)
        api.put(header, bytes(uc.mem_read(header, m.HEADER_SIZE)))
        return o.stats(), len(lookups)

    def test_all_85_guids_select_expected_longbow_audio_preserve_abi_and_source(self):
        mapping, _ = m.load_mapping()
        for entry in mapping:
            with self.subTest(source=entry[0]):
                stats, lookups = self.execute(entry)
                self.assertEqual(lookups, 1)
                self.assertEqual(stats['fire_swapped'], int(entry[2] == 1))
                self.assertEqual(stats['impact_swapped'], int(entry[2] == 2))
                self.assertEqual(stats['last_source_guid'], entry[0])
                self.assertEqual(stats['last_target_guid'], entry[1])
                self.assertEqual(stats['calls'], 1)
                self.assertEqual(stats['failed'], 0)
                self.assertEqual(stats['fallback'], 0)
                self.assertEqual(stats['generation'], 2)

    def test_identity_longbow_and_arrow_impacts_and_unlisted_guids_keep_original(self):
        config = json.loads((m.ROOT / 'silencer-audio-mode-map.json').read_text(encoding='utf8'))
        for guid in config['native_pass'] + ['00000000-0000-0000-0000-000000000000',
                                              '11111111-2222-3333-4444-555555555555']:
            with self.subTest(guid=guid):
                stats, lookups = self.execute(source_guid=guid)
                self.assertEqual(lookups, 0)
                self.assertEqual(stats['matched'], 0)

    def test_all_137_real_weapon_resource_bindings_are_mapped_or_target_identity(self):
        catalog = resource_catalog()
        config = json.loads((m.ROOT / 'silencer-audio-mode-map.json').read_text(encoding='utf8'))
        paths = {x['weapon'] for x in catalog['identities'] if any('/' + category + '/' in x['weapon']
                 for category in ('weapon_rifles_01', 'weapon_shotguns_01', 'weapon_handguns_01', 'weapon_bows_01'))}
        self.assertEqual(len(paths), 137)
        fire, impact = set(), set()
        per_weapon = {path: {'fire': set(), 'impact': set()} for path in paths}
        firing_effects = set()
        for definition in catalog['definitions']:
            if definition['weapon'] not in paths:continue
            effect = definition['effect']
            for guid in definition['guids'].values():
                if effect == 'Fire' or effect.startswith('Fire_'):
                    firing_effects.add(effect)
                    fire.add(guid)
                    per_weapon[definition['weapon']]['fire'].add((effect, guid))
                    with self.subTest(weapon=definition['weapon'], effect=effect, guid=guid):
                        self.assertTrue(guid in config['fire'] or guid == config['bow_fire'])
                elif effect == 'BulletImpact':
                    impact.add(guid)
                    per_weapon[definition['weapon']]['impact'].add(guid)
                    self.assertTrue(guid in config['impact'] or guid in config['native_pass'])
        for weapon, bindings in per_weapon.items():
            with self.subTest(weapon=weapon):
                self.assertTrue(bindings['fire'], 'No firing variant captured')
                self.assertTrue(bindings['impact'], 'No impact binding captured')
        self.assertEqual(firing_effects, {'Fire', 'Fire_1', 'Fire_2', 'Fire_3', 'Fire_410', 'Fire_45c'})
        self.assertEqual(len(fire), 74)
        self.assertEqual(len(impact), 24)
        self.assertEqual(len(set(config['native_pass'])), 13)

    def test_off_expiry_epoch_qpc_busy_and_invalid_source_binding_keep_original(self):
        for condition in ('off', 'expired', 'odd', 'epoch_race', 'qpc_fail', 'busy',
                          'missing_wrapper', 'missing_metadata', 'mismatched_metadata'):
            with self.subTest(condition=condition):
                stats, lookups = self.execute(condition=condition)
                self.assertEqual(lookups, 0)
                self.assertEqual(stats['fire_swapped'] + stats['impact_swapped'], 0)

    def test_missing_manager_and_lookup_late_binding_lease_errors_keep_original(self):
        cases = {'missing_manager': 1, 'bad_manager_low': 1, 'bad_manager_high': 1,
                 'wrong_vtable': 2, 'missing_studio': 3, 'lookup_fail': 4, 'lookup_empty': 5,
                 'changed_manager': 6, 'changed_studio': 6, 'late_qpc_fail': 7,
                 'late_expiry': 8, 'late_epoch_race': 8}
        for condition, reason in cases.items():
            with self.subTest(condition=condition):
                stats, lookups = self.execute(condition=condition)
                self.assertEqual(stats['fire_swapped'] + stats['impact_swapped'], 0)
                self.assertEqual(stats['reason'], reason)
                self.assertEqual(stats['fallback'], 1)
                self.assertEqual(stats['failed'], int(condition in ('lookup_fail', 'lookup_empty')))
                self.assertEqual(lookups, int(reason >= 4))

    def test_native_create_failure_is_returned_once_and_counted_without_retry(self):
        stats, lookups = self.execute(condition='create_failure')
        self.assertEqual(lookups, 1)
        self.assertEqual(stats['create_error'], 37)
        self.assertEqual(stats['reason'], 9)
        self.assertEqual(stats['failed'], 1)
        self.assertEqual(stats['fire_swapped'], 0)
        self.assertEqual(stats['fallback'], 0)

    def test_torn_stats_are_not_reported(self):
        api = FakeAPI()
        o = m.SilencerAudioMode(fixture(api), 1, api=api)
        o.install()
        api.put(o.allocation + m.CODE_SIZE + 344, struct.pack('<Q', 1))
        self.assertEqual(o.stats(), {})


if __name__ == '__main__':unittest.main(verbosity=2)
