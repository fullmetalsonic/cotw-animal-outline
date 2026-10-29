"""Minimal captured engine/resource fixtures; no installed-game dependency."""
import json
from pathlib import Path
import struct

FIXTURES=json.loads(Path(__file__).with_name('test_silencer_fixtures.json').read_text(encoding='utf-8'))
MASK=0xFFFFFFFF

def rot(value, bits):
    return ((value << bits) | (value >> (32 - bits))) & MASK


def hash32(text):
    # Jenkins lookup3, matching DECA hash32_func and the existing stringlookup ID.
    data = text.encode("ascii")
    a = b = c = (0xDEADBEEF + len(data)) & MASK
    position = 0
    while len(data) - position > 12:
        x, y, z = struct.unpack_from("<III", data, position)
        a, b, c = (a + x) & MASK, (b + y) & MASK, (c + z) & MASK
        a = ((a - c) ^ rot(c, 4)) & MASK; c = (c + b) & MASK
        b = ((b - a) ^ rot(a, 6)) & MASK; a = (a + c) & MASK
        c = ((c - b) ^ rot(b, 8)) & MASK; b = (b + a) & MASK
        a = ((a - c) ^ rot(c, 16)) & MASK; c = (c + b) & MASK
        b = ((b - a) ^ rot(a, 19)) & MASK; a = (a + c) & MASK
        c = ((c - b) ^ rot(b, 4)) & MASK; b = (b + a) & MASK
        position += 12
    tail = data[position:]
    if not tail:
        return c
    a = (a + int.from_bytes(tail[:4], "little")) & MASK
    b = (b + int.from_bytes(tail[4:8], "little")) & MASK
    c = (c + int.from_bytes(tail[8:12], "little")) & MASK
    c = ((c ^ b) - rot(b, 14)) & MASK
    a = ((a ^ c) - rot(c, 11)) & MASK
    b = ((b ^ a) - rot(a, 25)) & MASK
    c = ((c ^ b) - rot(b, 16)) & MASK
    a = ((a ^ c) - rot(c, 4)) & MASK
    b = ((b ^ a) - rot(a, 14)) & MASK
    return ((c ^ b) - rot(b, 24)) & MASK


def resource_catalog():
    return dict(identities=FIXTURES['identities'],
                definitions=[dict(FIXTURES['effects'][index],weapon=weapon)
                             for weapon,index in FIXTURES['effect_references']])
