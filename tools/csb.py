#!/usr/bin/env python3
"""CSB table containers ("CSB " magic): Q&A, summary, archive, telop, roll and
scenario-chart text tables.

Big-endian, UTF-8. A CSB is a spreadsheet: a pool of NUL-terminated strings
(STRP) plus rows of cells, every cell being a reference to a pool string by
ABSOLUTE FILE OFFSET. Numbers are stored as strings too ("60", "-1").

  0x00 "CSB "  0x04 FE FF 01 00  0x08 FF FF 00 00 (constant)
  0x0C u32 total cell count (= number of references in all rows)
  0x10 u8  widest row (cells), then 00 00 00
  0x14 u32 row count
  0x18 chunk "STRP": u32 size, u32 count, count NUL-terminated strings,
       zero padding to a 4-byte boundary (size includes the 8 byte chunk
       header and the padding)
  next chunk "LNP ": u32 size, u32 row count, then per row
       u32 n, u32 ptr (= file offset of the row's cell array, always the
       word right after this pair), n * u32 absolute offset of a STRP string
  next chunk "LNT ": u32 size (12 + 4 * rows), u32 row count,
       per row u32 absolute file offset of the row's "n" word
  The file ends with LNT. Strings are unique and every one is referenced.

Because everything after the string pool is absolute, build recomputes STRP
size, every row pointer and cell, the LNP/LNT sizes and the LNT table. Header
words are copied verbatim (counts do not change). The STRP padding bytes are
uninitialised garbage in some files and are reused when the pool is unchanged.

Worksheet: one entry per STRP string (id = pool index) that contains a
non-ASCII character; the rest (numbers, file names, ids, column titles) stays
untouched. "cell" is the first row/column that uses the string, "uses" the
number of cells that share it. `extract FILE OUT.json --all` lists every
string. Build leaves strings absent from the worksheet alone.

Usage:
  csb.py info FILE
  csb.py dump FILE [--all]
  csb.py extract FILE OUT.json [--all]
  csb.py build ORIGINAL IN.json OUT
  csb.py roundtrip PATH...         (files or directories; PASS/FAIL each)
  csb.py selftest FILE             (lengthen strings, rebuild, re-parse)
"""
import json
import os
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HDR = 0x18


def u32(d, o):
    return struct.unpack(">I", d[o:o + 4])[0]


def enc(s):
    return s.encode("utf-8") + b"\0"


def nonascii(s):
    return any(ord(c) > 127 for c in s)


# ---------------------------------------------------------------- parsing

def parse(d):
    """Parse a CSB. Raises ValueError on anything that is not the known layout."""
    if d[:4] != b"CSB " or d[4:12] != bytes.fromhex("feff0100ffff0000"):
        raise ValueError("not a CSB file")
    total_cells, widest, nrows = u32(d, 0x0C), d[0x10], u32(d, 0x14)
    if d[0x11:0x14] != bytes(3):
        raise ValueError("unexpected header bytes at 0x11")
    # STRP
    if d[HDR:HDR + 4] != b"STRP":
        raise ValueError("STRP chunk missing")
    ssize, scount = u32(d, HDR + 4), u32(d, HDR + 8)
    pos = HDR + 12
    strings, offs = [], []
    for _ in range(scount):
        e = d.index(b"\0", pos)
        offs.append(pos)
        strings.append(d[pos:e])
        pos = e + 1
    pool_end = pos
    pad = d[pool_end:HDR + ssize]
    if len(pad) != (-(pool_end - HDR)) % 4 or HDR + ssize != pool_end + len(pad):
        raise ValueError("STRP size/padding mismatch")
    index = {o: i for i, o in enumerate(offs)}
    # LNP
    lp = HDR + ssize
    if d[lp:lp + 4] != b"LNP ":
        raise ValueError("LNP chunk missing")
    lsize, lcount = u32(d, lp + 4), u32(d, lp + 8)
    if lcount != nrows:
        raise ValueError("row count mismatch")
    q = lp + 12
    rows, row_offs = [], []
    for _ in range(lcount):
        n, ptr = u32(d, q), u32(d, q + 4)
        if ptr != q + 8:
            raise ValueError("row pointer is not the following word at 0x%X" % q)
        cells = []
        for k in range(n):
            ref = u32(d, ptr + 4 * k)
            if ref not in index:
                raise ValueError("cell at 0x%X does not point at a string start" % (ptr + 4 * k))
            cells.append(index[ref])
        rows.append(cells)
        row_offs.append(q)
        q = ptr + 4 * n
    if q != lp + lsize:
        raise ValueError("LNP size mismatch")
    # LNT
    tp = q
    if d[tp:tp + 4] != b"LNT ":
        raise ValueError("LNT chunk missing")
    tsize, tcount = u32(d, tp + 4), u32(d, tp + 8)
    tab = [u32(d, tp + 12 + 4 * i) for i in range(tcount)]
    if tcount != nrows or tsize != 12 + 4 * tcount or tab != row_offs:
        raise ValueError("LNT does not list the row offsets")
    if tp + tsize != len(d):
        raise ValueError("trailing data after LNT")
    if sum(len(r) for r in rows) != total_cells or max([len(r) for r in rows] + [0]) != widest:
        raise ValueError("header cell count / width mismatch")
    return {
        "header": d[:HDR], "strings": strings, "str_offs": offs, "pad": pad,
        "rows": rows, "strp": (HDR, ssize), "lnp": (lp, lsize), "lnt": (tp, tsize),
    }


def serialize(header, strings, pad, rows):
    pool = b"".join(s + b"\0" for s in strings)
    if pad is None or len(pad) != (-(12 + len(pool))) % 4:
        pad = bytes((-(12 + len(pool))) % 4)
    strp = b"STRP" + struct.pack(">II", 12 + len(pool) + len(pad), len(strings)) + pool + pad
    offs, o = [], HDR + 12
    for s in strings:
        offs.append(o)
        o += len(s) + 1
    lp = HDR + len(strp)
    body = bytearray()
    row_offs = []
    for cells in rows:
        q = lp + 12 + len(body)
        row_offs.append(q)
        body += struct.pack(">II", len(cells), q + 8)
        for c in cells:
            body += struct.pack(">I", offs[c])
    lnp = b"LNP " + struct.pack(">II", 12 + len(body), len(rows)) + bytes(body)
    lnt = b"LNT " + struct.pack(">II", 12 + 4 * len(rows), len(rows)) + b"".join(
        struct.pack(">I", x) for x in row_offs)
    return header + strp + lnp + lnt


# ---------------------------------------------------------------- extract / build

def first_cells(p):
    first, uses = {}, {}
    for r, cells in enumerate(p["rows"]):
        for c, idx in enumerate(cells):
            first.setdefault(idx, (r, c))
            uses[idx] = uses.get(idx, 0) + 1
    return first, uses


def extract(path, all_strings=False):
    d = open(path, "rb").read()
    p = parse(d)
    first, uses = first_cells(p)
    entries = []
    for i, raw in enumerate(p["strings"]):
        s = raw.decode("utf-8")
        if not all_strings and not nonascii(s):
            continue
        e = {"id": i, "jp": s, "en": ""}
        if i in first:
            e["cell"] = "r%dc%d" % first[i]
        if uses.get(i, 0) > 1:
            e["uses"] = uses[i]
        entries.append(e)
    return {
        "file": os.path.basename(path),
        "format": "CSB",
        "pool_strings": len(p["strings"]),
        "untouched": "strings without non-ASCII characters (numbers, file names, ids)"
                     if not all_strings else "",
        "strings": entries,
    }


def build(orig_path, ws):
    d = open(orig_path, "rb").read()
    if ws.get("format") != "CSB":
        raise ValueError("worksheet format %r is not CSB" % ws.get("format"))
    p = parse(d)
    strings = list(p["strings"])
    for e in ws["strings"]:
        i = e["id"]
        if not 0 <= i < len(strings):
            raise ValueError("string id %s out of range" % i)
        if strings[i].decode("utf-8") != e["jp"]:
            raise ValueError("string id %s: jp text does not match the file" % i)
        en = e.get("en") or e["jp"]
        if "\0" in en:
            raise ValueError("NUL in translation id %s" % i)
        strings[i] = en.encode("utf-8")
    pad = p["pad"] if strings == p["strings"] else None   # keep garbage when unchanged
    out = serialize(p["header"], strings, pad, p["rows"])
    parse(out)                                             # re-parse end to end
    return out


# ---------------------------------------------------------------- commands

def first_diff(a, b):
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n


def iter_files(paths):
    for path in paths:
        if os.path.isdir(path):
            for root, _, files in os.walk(path):
                for f in sorted(files):
                    if f.lower().endswith(".csb"):
                        yield os.path.join(root, f)
        else:
            yield path


def roundtrip(paths):
    ok = bad = 0
    for path in iter_files(paths):
        try:
            orig = open(path, "rb").read()
            for label, ws in (("worksheet", extract(path)), ("all strings", extract(path, True))):
                out = build(path, ws)
                if out != orig:
                    raise ValueError("%s: first diff at 0x%X (sizes %d vs %d)" % (
                        label, first_diff(out, orig), len(out), len(orig)))
            p = parse(orig)
            if serialize(p["header"], p["strings"], p["pad"], p["rows"]) != orig:
                raise ValueError("serialize differs from original")
            print("PASS %s (%d translatable, %d pool strings, %d rows)" % (
                path, len(extract(path)["strings"]), len(p["strings"]), len(p["rows"])))
            ok += 1
        except Exception as e:  # noqa
            print("FAIL %s: %s" % (path, e))
            bad += 1
    print("roundtrip: %d pass, %d fail" % (ok, bad))
    return bad == 0


def selftest(path):
    d = open(path, "rb").read()
    p0 = parse(d)
    ws = extract(path)
    for i, e in enumerate(ws["strings"]):
        e["en"] = e["jp"] + "あ" * (1 + i % 7)
    out = build(path, ws)
    p1 = parse(out)
    assert p1["rows"] == p0["rows"], "row structure changed"
    exp = list(p0["strings"])
    for e in ws["strings"]:
        exp[e["id"]] = e["en"].encode("utf-8")
    assert p1["strings"] == exp
    print("selftest PASS %s: %d strings lengthened, %d -> %d bytes, %d rows / %d cells re-parsed" % (
        os.path.basename(path), len(ws["strings"]), len(d), len(out), len(p1["rows"]),
        sum(len(r) for r in p1["rows"])))
    return True


def cmd_info(path):
    d = open(path, "rb").read()
    p = parse(d)
    nonasc = sum(1 for s in p["strings"] if nonascii(s.decode("utf-8")))
    print("%s: %d bytes, CSB" % (path, len(d)))
    print("  header  cells=%d widest row=%d rows=%d" % (
        u32(d, 0x0C), d[0x10], u32(d, 0x14)))
    print("  STRP @0x%X size 0x%X  %d strings (%d non-ASCII), pad %s" % (
        p["strp"][0], p["strp"][1], len(p["strings"]), nonasc, p["pad"].hex() or "none"))
    print("  LNP  @0x%X size 0x%X  %d rows" % (p["lnp"][0], p["lnp"][1], len(p["rows"])))
    print("  LNT  @0x%X size 0x%X  ends at EOF" % (p["lnt"][0], p["lnt"][1]))


def cmd_dump(path, all_strings):
    ws = extract(path, all_strings)
    for e in ws["strings"]:
        print("%4d %-8s %s" % (e["id"], e.get("cell", ""), e["jp"].replace("\n", "\\n")))


def main(argv):
    flags = [a for a in argv if a.startswith("--")]
    args = [a for a in argv if not a.startswith("--")]
    cmd = args[1] if len(args) > 1 else ""
    if cmd == "info" and len(args) > 2:
        cmd_info(args[2])
    elif cmd == "dump" and len(args) > 2:
        cmd_dump(args[2], "--all" in flags)
    elif cmd == "extract" and len(args) > 3:
        ws = extract(args[2], "--all" in flags)
        os.makedirs(os.path.dirname(os.path.abspath(args[3])), exist_ok=True)
        with open(args[3], "w", encoding="utf-8", newline="\n") as f:
            json.dump(ws, f, ensure_ascii=False, indent=1)
        print("%s: %d strings" % (ws["file"], len(ws["strings"])))
    elif cmd == "build" and len(args) > 4:
        ws = json.load(open(args[3], encoding="utf-8"))
        out = build(args[2], ws)
        open(args[4], "wb").write(out)
        print("wrote %s (%d bytes)" % (args[4], len(out)))
    elif cmd == "roundtrip" and len(args) > 2:
        return 0 if roundtrip(args[2:]) else 1
    elif cmd == "selftest" and len(args) > 2:
        return 0 if selftest(args[2]) else 1
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
