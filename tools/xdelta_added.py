#!/usr/bin/env python3
"""Recover the data an xdelta3 (VCDIFF, RFC 3284) patch adds, without the
source file.

Every ADD/RUN instruction carries its bytes inside the patch, and COPYs
from earlier target output can be resolved too; only COPYs from the
source (the original disc) are unknown. This writes the target image
with unknown bytes zero-filled, plus a map of which ranges are known.
New text a translation patch inserts is ADD data, so it comes out intact.

Supports xdelta3's secondary compression with LZMA (id 2; each section is
varint(decoded size) + an .xz stream) and Adler-32 window checksums.

Usage: xdelta_added.py PATCH OUT_IMAGE [--map OUT.json]
"""
import json
import lzma
import struct
import sys

VCD_SOURCE, VCD_TARGET, VCD_ADLER32 = 1, 2, 4
NOOP, ADD, RUN, COPY = 0, 1, 2, 3


def build_code_table():
    """Default VCDIFF instruction code table (RFC 3284 section 5.6)."""
    t = []
    t.append(((RUN, 0, 0), (NOOP, 0, 0)))
    t.append(((ADD, 0, 0), (NOOP, 0, 0)))
    for s in range(1, 18):
        t.append(((ADD, s, 0), (NOOP, 0, 0)))
    for mode in range(9):
        t.append(((COPY, 0, mode), (NOOP, 0, 0)))
        for s in range(4, 19):
            t.append(((COPY, s, mode), (NOOP, 0, 0)))
    for mode in range(6):
        for a in range(1, 5):
            for c in range(4, 7):
                t.append(((ADD, a, 0), (COPY, c, mode)))
    for mode in range(6, 9):
        for a in range(1, 5):
            t.append(((ADD, a, 0), (COPY, 4, mode)))
    for mode in range(9):
        t.append(((COPY, 4, mode), (ADD, 1, 0)))
    assert len(t) == 256, len(t)
    return t


CODE = build_code_table()


class Reader:
    def __init__(self, b, pos=0):
        self.b, self.p = b, pos

    def byte(self):
        v = self.b[self.p]
        self.p += 1
        return v

    def varint(self):
        v = 0
        while True:
            c = self.byte()
            v = (v << 7) | (c & 0x7F)
            if not c & 0x80:
                return v

    def take(self, n):
        v = self.b[self.p:self.p + n]
        self.p += n
        return v


class Secondary:
    """xdelta3 keeps one LZMA stream per section type (data, inst, addr)
    open for the whole file and sync-flushes it after each window, so only
    the first section carries the .xz header; later ones continue it."""

    def __init__(self, comp_id):
        if comp_id != 2:
            raise ValueError("secondary compressor %d not supported" % comp_id)
        self.dec = {}

    def __call__(self, kind, section):
        r = Reader(section)
        size = r.varint()
        d = self.dec.setdefault(kind, lzma.LZMADecompressor(format=lzma.FORMAT_XZ))
        out = d.decompress(section[r.p:], max_length=size)
        if len(out) != size:
            raise ValueError("secondary size mismatch %d vs %d" % (len(out), size))
        return out


def decode(patch_path, out_path):
    p = open(patch_path, "rb").read()
    if p[:3] != b"\xd6\xc3\xc4":
        raise ValueError("not VCDIFF")
    r = Reader(p, 4)
    hdr = r.byte()
    comp_id = r.byte() if hdr & 1 else 0
    if hdr & 2:
        raise ValueError("custom code table not supported")
    app = r.take(r.varint()) if hdr & 4 else b""
    secondary = Secondary(comp_id) if comp_id else None
    known = []            # [start, end) ranges of target bytes we know
    out = open(out_path, "wb")
    tpos = 0
    windows = 0
    while r.p < len(p):
        win = r.byte()
        src_len = src_pos = 0
        if win & (VCD_SOURCE | VCD_TARGET):
            src_len, src_pos = r.varint(), r.varint()
        r.varint()                      # length of the delta encoding
        tlen = r.varint()
        delta_ind = r.byte()
        dlen, ilen, alen = r.varint(), r.varint(), r.varint()
        if win & VCD_ADLER32:
            r.take(4)
        data, inst, addr = r.take(dlen), r.take(ilen), r.take(alen)
        if delta_ind & 1:
            data = secondary("d", data)
        if delta_ind & 2:
            inst = secondary("i", inst)
        if delta_ind & 4:
            addr = secondary("a", addr)
        target = bytearray(tlen)
        tknown = bytearray(tlen)        # 1 = byte known
        dr, ir, ar = Reader(data), Reader(inst), Reader(addr)
        near, same = [0] * 4, [0] * (3 * 256)
        ni = 0
        here = 0
        while ir.p < len(inst):
            code = ir.byte()
            for typ, size, mode in CODE[code]:
                if typ == NOOP:
                    continue
                if size == 0:
                    size = ir.varint()
                if typ == ADD:
                    target[here:here + size] = dr.take(size)
                    tknown[here:here + size] = b"\x01" * size
                elif typ == RUN:
                    b = dr.byte()
                    target[here:here + size] = bytes([b]) * size
                    tknown[here:here + size] = b"\x01" * size
                else:
                    cur = src_len + here
                    if mode == 0:
                        a = ar.varint()
                    elif mode == 1:
                        a = cur - ar.varint()
                    elif 2 <= mode <= 5:
                        a = near[mode - 2] + ar.varint()
                    else:
                        a = same[(mode - 6) * 256 + ar.byte()]
                    near[ni] = a
                    ni = (ni + 1) % 4
                    same[a % (3 * 256)] = a
                    if a < src_len:
                        pass                    # from source: unknown, stays zero
                    else:
                        t0 = a - src_len
                        if t0 + size <= here:
                            target[here:here + size] = target[t0:t0 + size]
                            tknown[here:here + size] = tknown[t0:t0 + size]
                        else:                  # overlapping run: byte by byte
                            for k in range(size):
                                target[here + k] = target[t0 + k]
                                tknown[here + k] = tknown[t0 + k]
                here += size
        out.write(target)
        # record known ranges
        i = 0
        while i < tlen:
            if tknown[i]:
                j = tknown.find(b"\x00", i)
                j = tlen if j < 0 else j
                if known and known[-1][1] == tpos + i:
                    known[-1][1] = tpos + j
                else:
                    known.append([tpos + i, tpos + j])
                i = j
            else:
                j = tknown.find(b"\x01", i)
                i = tlen if j < 0 else j
        tpos += tlen
        windows += 1
    out.close()
    return {"app_header": app.decode("latin-1"), "windows": windows, "target_size": tpos,
            "known_bytes": sum(b - a for a, b in known), "known_ranges": known}


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    info = decode(argv[1], argv[2])
    if "--map" in argv:
        json.dump(info, open(argv[argv.index("--map") + 1], "w"))
    print("app header: %s" % info["app_header"])
    print("%d windows, target %d bytes, %d bytes known from the patch (%d ranges)" % (
        info["windows"], info["target_size"], info["known_bytes"], len(info["known_ranges"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
