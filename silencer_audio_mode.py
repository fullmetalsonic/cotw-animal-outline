"""Leased weapon audio replacement; import never accesses the game.

Only the signed FMOD createInstance argument changes. Existing metadata distance
and parameter defaults remain the source weapon's defaults; no ballistics are written.
Target is longbow fire plus pure bow impacts. Longbow's exceptional native gun
reference at material field 06b2eee0 is intentionally not retained.
Recording counters describe native success, not listening or waveform verification.
"""
import hashlib
import json
from pathlib import Path
import struct
import threading
import uuid

ROOT = Path(__file__).resolve().parent
import game_memory as probe
from native_game import ALLOCATION_SIZE, NativeAPI, rel_call

CALL_RVA, ORIGINAL_RVA, LOOKUP_RVA, QPC_IAT_RVA = 0x29F419, 0x15C5554, 0x15C54D6, 0x1920518
MANAGER_RVA, MANAGER_VTABLE_RVA = 0x27B8D28, 0x197EFF8
ORIGINAL_CALL = rel_call(CALL_RVA, ORIGINAL_RVA)
CODE_SIZE, HEADER_SIZE, MAP_OFFSET, MAP_ENTRY_SIZE = 8192, 512, 4096, 40
LEASE_SECONDS = .3
MAGIC = b'COTW_SIL_AUDIO_1'.ljust(16, b'\0')
STUB_SHA256 = '1ef32d2cb4583985210487e657233f468388b919fc2672b59a5a0d18096e9a6e'
SIGNATURES = {
    0x29F411: bytes.fromhex('488d542450488b0b'),
    0x29F41E: bytes.fromhex('85c00f85c9000000'),
    ORIGINAL_RVA: bytes.fromhex('ff253ec23500'),
    LOOKUP_RVA: bytes.fromhex('ff2534c43500'),
    0x273B20: bytes.fromhex('488d05d1b47001488907'),
    0x29E746: bytes.fromhex('488b0ddba55102'),
}


def load_mapping(path=None):
    mapping = json.loads((Path(path) if path else ROOT / 'silencer-audio-mode-map.json').read_text(encoding='utf8'))
    if mapping.get('version') != 1 or len(mapping['fire']) != 73 or len(mapping['impact']) != 12:
        raise ValueError('Unsupported silencer mapping')
    entries = [(source, mapping['bow_fire'], 1) for source in mapping['fire']]
    entries += [(source, target, 2) for source, target in mapping['impact'].items()]
    sources = [source for source, _, _ in entries]
    if len(set(sources)) != 85 or mapping['bow_fire'] in sources:
        raise ValueError('Ambiguous silencer mapping')
    raw = b''.join(uuid.UUID(source).bytes_le + uuid.UUID(target).bytes_le + struct.pack('<II', kind, 0)
                   for source, target, kind in entries)
    return entries, raw


class SilencerAudioMode:
    def __init__(self, game, writer, *, api=None, code=None):
        self.game, self.writer = game, writer
        self.api = api if api is not None else NativeAPI(game, writer)
        self.code = code if code is not None else Path(__file__).with_suffix('.bin').read_bytes()
        self.mapping, self.mapping_bytes = load_mapping()
        if (len(self.code) != CODE_SIZE or hashlib.sha256(self.code).hexdigest() != STUB_SHA256
                or self.code[MAP_OFFSET:MAP_OFFSET + len(self.mapping_bytes)] != self.mapping_bytes):
            raise ValueError('Silencer audio binary/mapping mismatch')
        self.allocation, self.sequence = None, 0
        self.lock = threading.RLock()

    @property
    def site(self):
        return self.game.base + CALL_RVA

    def _header(self):
        raw = bytearray(HEADER_SIZE)
        raw[:16] = MAGIC
        struct.pack_into('<II5Q', raw, 16, 1, len(self.mapping), self.game.base,
                         self.game.base + QPC_IAT_RVA, self.game.base + ORIGINAL_RVA,
                         self.game.base + LOOKUP_RVA, self.site)
        raw[96:128] = hashlib.sha256(self.code).digest()
        raw[128:160] = bytes.fromhex(probe.EXPECTED_SHA256)
        struct.pack_into('<4Q', raw, 160, self.game.base + MANAGER_RVA,
                         self.game.base + MANAGER_VTABLE_RVA, CODE_SIZE, ALLOCATION_SIZE)
        raw[192:224] = hashlib.sha256(self.mapping_bytes).digest()
        return bytes(raw)

    def _verify_owned(self, allocation):
        if not 0x10000 <= allocation <= 0x7FFFFFFFFFFF - ALLOCATION_SIZE or allocation & 0xFFFF:
            raise RuntimeError('Invalid silencer allocation')
        actual, expected = self.api.read(allocation + CODE_SIZE, HEADER_SIZE), self._header()
        if (actual[:64] != expected[:64] or actual[96:224] != expected[96:224]
                or actual[368:] != expected[368:] or self.api.read(allocation, CODE_SIZE) != self.code):
            raise RuntimeError('Silencer audio ownership mismatch')
        self.sequence = struct.unpack_from('<Q', actual, 64)[0]

    def _check(self):
        for rva, expected in SIGNATURES.items():
            if self.api.read(self.game.base + rva, len(expected)) != expected:
                raise RuntimeError('Silencer audio native signature mismatch')
        raw = self.api.read(self.site, 5)
        if raw == ORIGINAL_CALL:
            return None
        if raw[:1] == b'\xe8':
            allocation = self.site + 5 + struct.unpack('<i', raw[1:])[0]
            self._verify_owned(allocation)
            return allocation
        raise RuntimeError('Foreign FMOD createInstance CALL patch')

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
                self.api.write(self.allocation, self.code)
                self.api.write(self.allocation + CODE_SIZE, self._header())
                self._verify_owned(self.allocation)
                self.api.protect(self.allocation, CODE_SIZE, 0x20)
                self.api.flush(self.allocation, CODE_SIZE)
            else:
                self._verify_owned(self.allocation)
            self.disable()
            self._change_call(ORIGINAL_CALL, rel_call(self.site, self.allocation))

    def _change_call(self, before, after):
        with self.api.frozen_threads(self.site, 5):
            self._check()
            if self.api.read(self.site, 5) != before:
                raise RuntimeError('FMOD createInstance CALL changed during transaction')
            old = self.api.protect(self.site, 5, 0x40)
            try:
                self.api.write(self.site, after)
                if self.api.read(self.site, 5) != after:
                    raise OSError('Silencer postimage mismatch')
                self.api.flush(self.site, 5)
                self.api.protect(self.site, 5, old)
            except Exception as error:
                try:
                    self.api.protect(self.site, 5, 0x40)
                    self.api.write(self.site, before)
                    if self.api.read(self.site, 5) != before:
                        raise OSError('Silencer rollback mismatch')
                    self.api.flush(self.site, 5)
                    self.api.protect(self.site, 5, old)
                except Exception as rollback_error:
                    raise RuntimeError('Silencer rollback failed; stop the game') from rollback_error
                raise RuntimeError('Silencer transaction failed; previous CALL restored') from error

    def _lease(self, deadline):
        header = self.allocation + CODE_SIZE
        self.sequence = ((self.sequence + 2) & 0xFFFFFFFFFFFFFFFE) or 2
        self.api.write(header + 64, struct.pack('<Q', self.sequence - 1))
        try:
            self.api.write(header + 72, struct.pack('<Q', deadline))
            self.api.write(header + 64, struct.pack('<Q', self.sequence))
        except Exception:
            try:
                self.api.write(header + 72, bytes(8))
            except OSError:
                pass
            raise

    def publish(self):
        with self.lock:
            try:
                if self.allocation is None:
                    self.install()
                if self._check() != self.allocation:
                    raise RuntimeError('Silencer audio is not installed')
                now, frequency = self.api.clock()
                self._lease(now + int(frequency * LEASE_SECONDS))
                return 1
            except Exception:
                self.disable()
                raise

    def disable(self):
        with self.lock:
            if self.allocation is not None:
                try:
                    self._lease(0)
                except OSError:
                    if self.api.is_running():
                        raise

    def close(self):
        with self.lock:
            try:
                self.disable()
                if self.allocation is not None:
                    owned = self._check()
                    if owned == self.allocation:
                        self._change_call(rel_call(self.site, owned), ORIGINAL_CALL)
            except OSError:
                if self.api.is_running():
                    raise
            # Keep allocation alive until process exit for in-flight native calls.

    def stats(self):
        with self.lock:
            if self.allocation is None:
                return {}
            address = self.allocation + CODE_SIZE
            raw = self.api.read(address, HEADER_SIZE)
            sequence = struct.unpack_from('<Q', raw, 344)[0]
            if sequence & 1 or self.api.read(address + 344, 8) != struct.pack('<Q', sequence):
                return {}
            result = {name: struct.unpack_from('<Q', raw, offset)[0] for name, offset in (
                ('calls', 80), ('fire_swapped', 224), ('impact_swapped', 232), ('failed', 240),
                ('fallback', 248), ('last_source_desc', 288), ('last_target_desc', 296),
                ('last_qpc', 312), ('last_manager', 320), ('last_studio', 328), ('last_epoch', 336),
                ('generation', 344), ('matched', 352))}
            for name, offset in (('lookup_error', 304), ('last_kind', 308), ('reason', 360), ('create_error', 364)):
                result[name] = struct.unpack_from('<I', raw, offset)[0]
            result['last_source_guid'] = str(uuid.UUID(bytes_le=raw[256:272]))
            result['last_target_guid'] = str(uuid.UUID(bytes_le=raw[272:288]))
            return result
