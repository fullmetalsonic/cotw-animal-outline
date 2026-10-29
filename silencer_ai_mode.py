"""Leased local-weapon AI profile substitution; game data stays original."""
from contextlib import ExitStack
import hashlib
from pathlib import Path
import struct
import threading

import game_memory as probe
from native_game import NativeAPI, ALLOCATION_SIZE, rel_call
from ninja_mode import NinjaMode, TransientNinjaState

CALLS = ((0x62B22B, 0, 0x5ED810), (0x62B391, 64, 0x5EC420))
ORIGINAL_CALLS = tuple(rel_call(rva, original) for rva, _, original in CALLS)
CODE_SIZE, HEADER_SIZE = 8192, 512
MAGIC = b"COTW_SIL_AI_V1".ljust(16, b"\0")
STUB_SHA256 = "41574f3c7c2a3ba79fdbf4f030189f6729509d39f660e5b0ff0393d37a543b2f"
LONG_BOW_HASH = 0xBD9568A5
LONG_BOW_VALUES = struct.pack("<7f", 75., 10., 2., 50., 25., 1., 250.)
SIGNATURES = {
    0x62B221: bytes.fromhex("448b877c010000498bcd"),
    0x62B387: bytes.fromhex("448b87dc010000498bcd"),
    0x62B1CC: bytes.fromhex("8b9f78010000"),
    0x62B332: bytes.fromhex("8b9fd8010000"),
    0x5ED810: bytes.fromhex("4c8b8988030000498bd1498b41088078"),
    0x5EC420: bytes.fromhex("4c8b8988030000498bd1498b41088078"),
}


class SilencerAiMode:
    def __init__(self, game, writer, *, api=None, code=None):
        self.game, self.writer = game, writer
        self.api = api or NativeAPI(game, writer)
        self.code = code if code is not None else Path(__file__).with_suffix(".bin").read_bytes()
        if len(self.code) != CODE_SIZE or hashlib.sha256(self.code).hexdigest() != STUB_SHA256:
            raise ValueError("Silencer AI binary mismatch")
        self.allocation, self.sequence = None, 0
        self.lock = threading.RLock()
        self._local = NinjaMode(game,writer,api=self.api)

    @property
    def sites(self):
        return tuple(self.game.base+rva for rva, _, _ in CALLS)

    def _q(self, address):
        return struct.unpack("<Q", self.api.read(address, 8))[0]

    def _header(self):
        h = bytearray(HEADER_SIZE)
        h[:16] = MAGIC
        struct.pack_into("<II5Q", h, 16, 1, 0, self.game.base,
                         self.game.base+0x1920518, self.game.base+CALLS[0][2],
                         self.game.base+CALLS[1][2], self.game.base+0x27C5D30)
        struct.pack_into("<3Q", h, 112, self.game.base+0x27F1478,
                         self.game.base+0x1A60028, self.game.base+0x1EE24A0)
        struct.pack_into("<II", h, 136, LONG_BOW_HASH, 137)
        h[192:224] = hashlib.sha256(self.code).digest()
        h[224:256] = bytes.fromhex(probe.EXPECTED_SHA256)
        return bytes(h)

    def _verify_owned(self, allocation):
        if not 0x10000 <= allocation <= 0x7FFFFFFFFFFF-ALLOCATION_SIZE or allocation & 0xFFFF:
            raise RuntimeError("Invalid silencer AI allocation")
        actual = self.api.read(allocation+CODE_SIZE, HEADER_SIZE)
        expected = self._header()
        immutable = ((0,64),(112,144),(152,256),(320,512))
        if (any(actual[a:b] != expected[a:b] for a,b in immutable)
                or self.api.read(allocation,CODE_SIZE) != self.code):
            raise RuntimeError("Silencer AI ownership mismatch")
        self.sequence = struct.unpack_from("<Q", actual, 64)[0]

    def _check(self):
        for rva, expected in SIGNATURES.items():
            if self.api.read(self.game.base+rva,len(expected)) != expected:
                raise RuntimeError("Native AI calculation differs")
        owners = []
        for site, (_,entry,_), original in zip(self.sites,CALLS,ORIGINAL_CALLS):
            raw = self.api.read(site,5)
            if raw == original:
                owners.append(None)
            elif raw[:1] == b"\xe8":
                allocation = site+5+struct.unpack("<i",raw[1:])[0]-entry
                self._verify_owned(allocation)
                owners.append(allocation)
            else:
                raise RuntimeError("Foreign silencer AI patch")
        if owners[0] != owners[1]:
            raise RuntimeError("Partial silencer AI patch")
        return owners[0]

    def _patched(self, allocation):
        return tuple(rel_call(site,allocation+entry) for site,(_,entry,_) in zip(self.sites,CALLS))

    def _change_calls(self, before, after):
        with ExitStack() as stack:
            for site in self.sites:
                stack.enter_context(self.api.frozen_threads(site,5))
            self._check()
            if any(self.api.read(site,5) != raw for site,raw in zip(self.sites,before)):
                raise RuntimeError("AI calculation CALL changed during transaction")
            protections = {}
            try:
                for site, raw in zip(self.sites,after):
                    protections[site] = self.api.protect(site,5,0x40)
                    self.api.write(site,raw)
                    self.api.flush(site,5)
                    self.api.protect(site,5,protections[site])
            except Exception as error:
                try:
                    for site,raw in zip(self.sites,before):
                        old = self.api.protect(site,5,0x40)
                        self.api.write(site,raw)
                        self.api.flush(site,5)
                        self.api.protect(site,5,protections.get(site,old))
                except Exception as rollback_error:
                    raise RuntimeError("Silencer AI rollback failed; stop the game") from rollback_error
                raise RuntimeError("Silencer AI transaction failed; previous calls restored") from error

    def install(self):
        with self.lock:
            owned = self._check()
            if hashlib.sha256(self.game.exe.read_bytes()).hexdigest() != probe.EXPECTED_SHA256:
                raise RuntimeError("Unsupported game executable")
            if owned is not None:
                self.allocation = owned
                self.disable()
                return
            if self.allocation is None:
                self.allocation = self.api.allocate_near(self.sites[0])
                self.api.write(self.allocation,self.code)
                self.api.write(self.allocation+CODE_SIZE,self._header())
                self._verify_owned(self.allocation)
                self.api.protect(self.allocation,CODE_SIZE,0x20)
                self.api.flush(self.allocation,CODE_SIZE)
            else:
                self._verify_owned(self.allocation)
            self.disable()
            self._change_calls(ORIGINAL_CALLS,self._patched(self.allocation))

    def _binding(self):
        b = self._local._binding()
        manager = self._q(self.game.base+0x27C5D30)
        if not manager:
            raise TransientNinjaState("AI sound profile manager is changing")
        host = self._q(manager+0x220)
        if not host:
            raise TransientNinjaState("AI sound profile is changing")
        head = self._q(host+0x388)
        if not head:
            raise RuntimeError("AI weapon profiles unavailable")
        root = self._q(head+8)
        node = root
        for _ in range(64):
            raw = self.api.read(node,0x40)
            if raw[0x19]:
                raise RuntimeError("Native longbow AI profile missing")
            key = struct.unpack_from("<I",raw,0x1C)[0]
            if key == LONG_BOW_HASH:
                if raw[0x20:0x3C] != LONG_BOW_VALUES:
                    raise RuntimeError("Native longbow AI profile differs")
                break
            node = struct.unpack_from("<Q",raw,0 if LONG_BOW_HASH < key else 0x10)[0]
        else:
            raise RuntimeError("AI weapon profile tree invalid")
        if (self._q(host+0x388) != head or self._q(head+8) != root
                or self._q(manager+0x220) != host
                or self._q(self.game.base+0x27C5D30) != manager):
            raise TransientNinjaState("AI sound profile changed during binding")
        return dict(b,host=host,bow_node=node)

    def _lease(self, deadline, binding=None):
        header = self.allocation+CODE_SIZE
        self.sequence = ((self.sequence+2)&0xFFFFFFFFFFFFFFFE) or 2
        self.api.write(header+64,struct.pack("<Q",self.sequence-1))
        try:
            if binding:
                self.api.write(header+80,struct.pack("<4Q",binding["character"],binding["handle"],
                                                   binding["host"],binding["bow_node"]))
                self.api.write(header+144,struct.pack("<Q",binding["player"]))
            self.api.write(header+72,struct.pack("<Q",deadline))
            self.api.write(header+64,struct.pack("<Q",self.sequence))
        except Exception:
            self.api.write(header+72,bytes(8))
            raise

    def publish(self):
        with self.lock:
            try:
                if self.allocation is None:
                    self.install()
                if self._check() != self.allocation:
                    raise RuntimeError("Silencer AI not attached")
                binding = self._binding()
                now,frequency = self.api.clock()
                self._lease(now+int(frequency*.3),binding)
            except Exception:
                self.disable()
                raise

    def disable(self):
        with self.lock:
            if self.allocation is not None:
                self._lease(0)

    def close(self):
        with self.lock:
            try:
                self.disable()
                if self.allocation is not None and self._check() == self.allocation:
                    self._change_calls(self._patched(self.allocation),ORIGINAL_CALLS)
            except OSError:
                if self.api.is_running():
                    raise
            # Entered wrappers finish safely from retained private allocation.

    def read_stats(self):
        if self.allocation is None:
            return {}
        return dict(zip(("total","fire_swapped","impact_swapped","fallback","last_weapon","last_source","qpc"),
                        struct.unpack("<7Q",self.api.read(self.allocation+CODE_SIZE+256,56))))
