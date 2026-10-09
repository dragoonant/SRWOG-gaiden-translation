#!/usr/bin/env python3
"""Story script containers: LDBI (Dat/logic/talk/ls*.bin) and LOGO (Dat/logic/scr*.bin).

Both are big-endian with UTF-8, NUL-terminated strings referenced by INDEX
from fixed-size records, so string pools can be rebuilt freely.

LDBI (talk / dialogue):
  0x00 "LDBI"  0x04 u32 1000 (version)
  0x08 u32 0   0x0C u32 string_count (includes string 0 = "")
  0x10 u32 1   0x14 u32 offset of string offset table
  0x18 u32 0x30  0x1C u32 offset of section 2 (0x1A80 bytes, constant)
  0x20 u32 n3    0x24 u32 offset of section 3 (4 + n3 * 132 bytes)
  0x28 u32 n4    0x2C u32 offset of section 4 (4 + n4 * 12 bytes)
  0x30..0x80 little-endian editor metadata, kept verbatim
  0x80 string pool: string_count NUL-terminated UTF-8 strings, first is ""
  offset table: string_count u32 ABSOLUTE file offsets
  pool and table are zero-padded to a 128-byte boundary, and always get at
  least one byte of padding (a full 128-byte block when already aligned).
  Section 3 records hold the dialogue commands: words 1..3 are string
  indices (speaker label "[ＤＭ]-name", line text ...). Section 4 is the
  cast list (type, 2n, name string index).

LOGO (stage logic):
  0x00 "LOGO"  0x04 u32 file_size  0x08 u32 0  0x0C u32 0
  0x10.. (count, offset) pairs for ten sections; the string ones are
  0x40 (nA, tableA)  0x48 (nA, poolA)  0x50 (nB+1, tableB)  0x58 (nB, poolB)
  0x6C u32 file_size again. Other header words are kept verbatim.
  tableA: nA u32 offsets relative to poolA; tableB: nB+1 offsets relative
  to poolA, the last one being the end of the strings.
  tableA and tableB are contiguous; the table region is padded to 64 bytes
  from tableA, then poolA and poolB are contiguous and the pool region is
  padded to 64 bytes from poolA. Padding is 0xAD up to the next 4-byte
  boundary, then little-endian u32 0xDEADDEAD words (AD DE AD DE). The
  bytes before the boundary are uninitialised garbage in 5 of 102 files,
  so an unchanged pool keeps the original fill bytes verbatim.
  Pool A holds the "[ＤＭ]-name" speaker/unit labels, pool B holds stage
  text (talk file name, victory conditions with <W=..></W> tags, etc).

Usage:
  script.py extract FILE OUT.json
  script.py build   ORIGINAL IN.json OUT
  script.py roundtrip DIR      (extract+build every ls*/scr* file, compare)
  script.py dump FILE          (print strings)
"""
import json
import os
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEAD = b"\xde\xad"


def pad_to(n, align):
    return (n + align - 1) // align * align


def dead_fill(start, length):
    """Fill as the original packer did: bytes before the next 4-byte boundary
    are 0xAD, then little-endian u32 0xDEADDEAD (AD DE AD DE) per word."""
    out = bytearray()
    for p in range(start, start + length):
        if p < pad_to(start, 4):
            out.append(0xAD)
        else:
            out.append(0xAD if p % 2 == 0 else 0xDE)
    return bytes(out)


def pad_always(n, align):
    """LDBI regions always get padding, a full block when already aligned."""
    return n + (align - n % align)


def read_cstrings(data, start, count):
    out = []
    pos = start
    for _ in range(count):
        end = data.index(b"\0", pos)
        out.append(data[pos:end].decode("utf-8"))
        pos = end + 1
    return out, pos


def enc(s):
    return s.encode("utf-8") + b"\0"


# ---------------------------------------------------------------- LDBI

def ldbi_parse(data):
    assert data[:4] == b"LDBI"
    h = struct.unpack(">10I", data[8:0x30])
    count, off_tab, off2, off3, off4 = h[1], h[3], h[5], h[7], h[9]
    strings, end = read_cstrings(data, 0x80, count)
    tab = struct.unpack(">%dI" % count, data[off_tab:off_tab + 4 * count])
    return {
        "count": count, "off_tab": off_tab, "off2": off2, "off3": off3, "off4": off4,
        "strings": strings, "pool_end": end, "table": tab,
    }


def ldbi_extract(data):
    p = ldbi_parse(data)
    # Sanity: the table must point at exactly the strings we walked.
    pos = 0x80
    for i, s in enumerate(p["strings"]):
        if p["table"][i] != pos:
            raise ValueError("LDBI offset table mismatch at string %d" % i)
        pos += len(s.encode("utf-8")) + 1
    return [{"id": i, "jp": s, "en": ""} for i, s in enumerate(p["strings"])]


def ldbi_build(orig, entries):
    p = ldbi_parse(orig)
    if len(entries) != p["count"]:
        raise ValueError("string count changed: %d vs %d" % (len(entries), p["count"]))
    pool = bytearray()
    table = []
    for e in entries:
        table.append(0x80 + len(pool))
        pool += enc(e["en"] if e.get("en") else e["jp"])
    pool_len = pad_always(0x80 + len(pool), 128)
    pool += bytes(pool_len - 0x80 - len(pool))
    off_tab = 0x80 + len(pool)
    tab = struct.pack(">%dI" % len(table), *table)
    tab += bytes(pad_always(off_tab + len(tab), 128) - off_tab - len(tab))
    new_off2 = off_tab + len(tab)
    delta = new_off2 - p["off2"]
    hdr = bytearray(orig[:0x80])
    struct.pack_into(">I", hdr, 0x14, off_tab)
    struct.pack_into(">I", hdr, 0x1C, p["off2"] + delta)
    struct.pack_into(">I", hdr, 0x24, p["off3"] + delta)
    struct.pack_into(">I", hdr, 0x2C, p["off4"] + delta)
    return bytes(hdr) + bytes(pool) + tab + orig[p["off2"]:]


# ---------------------------------------------------------------- LOGO

def logo_parse(data):
    assert data[:4] == b"LOGO"
    nA, tabA, nA2, poolA, nB1, tabB, nB, poolB = struct.unpack(">8I", data[0x40:0x60])
    if nA != nA2 or nB1 != nB + 1:
        raise ValueError("LOGO string header inconsistent")
    tA = struct.unpack(">%dI" % nA, data[tabA:tabA + 4 * nA])
    tB = struct.unpack(">%dI" % nB1, data[tabB:tabB + 4 * nB1])
    sA, endA = read_cstrings(data, poolA, nA)
    sB, endB = read_cstrings(data, poolB, nB)
    return {"nA": nA, "nB": nB, "tabA": tabA, "tabB": tabB, "poolA": poolA, "poolB": poolB,
            "tA": tA, "tB": tB, "sA": sA, "sB": sB, "endA": endA, "endB": endB}


def logo_extract(data):
    p = logo_parse(data)
    pos = 0
    for i, s in enumerate(p["sA"]):
        if p["tA"][i] != pos:
            raise ValueError("LOGO table A mismatch at %d" % i)
        pos += len(s.encode("utf-8")) + 1
    if p["poolB"] != p["poolA"] + pos:
        raise ValueError("LOGO pool B not contiguous with pool A")
    for i, s in enumerate(p["sB"]):
        if p["tB"][i] != pos:
            raise ValueError("LOGO table B mismatch at %d" % i)
        pos += len(s.encode("utf-8")) + 1
    if p["tB"][-1] != pos:
        raise ValueError("LOGO table B end sentinel mismatch")
    out = [{"id": i, "pool": "A", "jp": s, "en": ""} for i, s in enumerate(p["sA"])]
    out += [{"id": i, "pool": "B", "jp": s, "en": ""} for i, s in enumerate(p["sB"])]
    return out


def logo_build(orig, entries):
    p = logo_parse(orig)
    a = [e for e in entries if e["pool"] == "A"]
    b = [e for e in entries if e["pool"] == "B"]
    if len(a) != p["nA"] or len(b) != p["nB"]:
        raise ValueError("string count changed")
    pool = bytearray()
    tA, tB = [], []
    for e in a:
        tA.append(len(pool))
        pool += enc(e["en"] if e.get("en") else e["jp"])
    poolB_rel = len(pool)
    for e in b:
        tB.append(len(pool))
        pool += enc(e["en"] if e.get("en") else e["jp"])
    tB.append(len(pool))
    tables = struct.pack(">%dI" % len(tA), *tA) + struct.pack(">%dI" % len(tB), *tB)
    tabA = p["tabA"]
    tables_padded = pad_to(len(tables), 64)
    orig_tables_len = p["tabB"] + 4 * (p["nB"] + 1) - tabA
    if len(tables) == orig_tables_len:
        tables += orig[tabA + len(tables):p["poolA"]]   # keep original fill bytes
    else:
        tables += dead_fill(tabA + len(tables), tables_padded - len(tables))
    pool_padded = pad_to(len(pool), 64)
    if len(pool) == p["endB"] - p["poolA"]:
        pool += orig[p["endB"]:]                        # keep original fill bytes
    else:
        pool += dead_fill(tabA + len(tables) + len(pool), pool_padded - len(pool))
    tabB = tabA + 4 * len(tA)
    poolA = tabA + len(tables)
    poolB = poolA + poolB_rel
    size = poolA + len(pool)
    hdr = bytearray(orig[:tabA])
    struct.pack_into(">I", hdr, 0x04, size)
    struct.pack_into(">I", hdr, 0x44, tabA)
    struct.pack_into(">I", hdr, 0x4C, poolA)
    struct.pack_into(">I", hdr, 0x54, tabB)
    struct.pack_into(">I", hdr, 0x5C, poolB)
    struct.pack_into(">I", hdr, 0x6C, size)
    return bytes(hdr) + tables + bytes(pool)


# ---------------------------------------------------------------- generic

def detect(data):
    if data[:4] == b"LDBI":
        return "LDBI"
    if data[:4] == b"LOGO":
        return "LOGO"
    raise ValueError("unknown script container %r" % data[:4])


def extract(path):
    data = open(path, "rb").read()
    fmt = detect(data)
    entries = ldbi_extract(data) if fmt == "LDBI" else logo_extract(data)
    return {"file": os.path.basename(path), "format": fmt, "strings": entries}


def build(orig_path, ws):
    orig = open(orig_path, "rb").read()
    fmt = detect(orig)
    if ws["format"] != fmt:
        raise ValueError("worksheet format %s does not match file %s" % (ws["format"], fmt))
    return ldbi_build(orig, ws["strings"]) if fmt == "LDBI" else logo_build(orig, ws["strings"])


def roundtrip(dirpath):
    ok = bad = 0
    nstr = 0
    for root, _, files in os.walk(dirpath):
        for f in sorted(files):
            if not (f.startswith("ls") or f.startswith("scr")) or not f.endswith(".bin"):
                continue
            path = os.path.join(root, f)
            try:
                ws = extract(path)
                out = build(path, ws)
                orig = open(path, "rb").read()
                if out == orig:
                    ok += 1
                    nstr += len(ws["strings"])
                else:
                    bad += 1
                    i = next((k for k in range(min(len(out), len(orig))) if out[k] != orig[k]), min(len(out), len(orig)))
                    print("FAIL %s: first diff at 0x%X (sizes %d vs %d)" % (path, i, len(out), len(orig)))
            except Exception as e:  # noqa
                bad += 1
                print("ERROR %s: %s" % (path, e))
    print("roundtrip: %d identical, %d failed, %d strings" % (ok, bad, nstr))
    return bad == 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "extract":
        ws = extract(argv[2])
        with open(argv[3], "w", encoding="utf-8", newline="\n") as f:
            json.dump(ws, f, ensure_ascii=False, indent=1)
        print("%s: %d strings" % (ws["file"], len(ws["strings"])))
    elif cmd == "build":
        ws = json.load(open(argv[3], encoding="utf-8"))
        out = build(argv[2], ws)
        open(argv[4], "wb").write(out)
        print("wrote %s (%d bytes)" % (argv[4], len(out)))
    elif cmd == "roundtrip":
        return 0 if roundtrip(argv[2]) else 1
    elif cmd == "dump":
        ws = extract(argv[2])
        for e in ws["strings"]:
            print("%s%4d  %s" % (e.get("pool", ""), e["id"], e["jp"]))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
