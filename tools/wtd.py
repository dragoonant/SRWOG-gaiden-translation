#!/usr/bin/env python3
"""WTD window/menu layout containers ("_DTW", General2d windowdataMain.wtd and
Logic areamapwindow.wtd).

Big-endian, UTF-8. A serialized widget tree; there is no string table. Every
string is u32 length (including the NUL) + bytes + zero padding up to the next
4-byte boundary of the FILE (an empty string is just the u32 0, no padding).

Layout:
  0x00 "_DTW"   0x04 u32 0x10 (constant)
  0x08 section "textures"  u16 0xFFFF, u16 n; n strings (name or empty)
       section "palette"   u16 0xFFFF, u16 n; n * 4 u16 (colour quads, 10000 = 1.0)
       section "anims"     u16 0xFFFF, u16 n; n * (u16 k, u16 total, k * (u16 id, u16 time))
       section "elements"  u16 0xFFFF, u16 n; n elements back to back to EOF
  element = u32 SIZE (bytes from this word to the next element, includes
            everything nested in it and every string) + SIZE-4 bytes of body.
  SIZE is the ONLY field in the file that depends on string length. All other
  size-looking words (0x40, 0x50, 0x140, 0x240 ...) are per-class constants
  (see docs/formats-csb-wtd.md), and the file has no absolute offsets.

The body of an element is a flag-driven record soup that is not fully decoded;
display text is found by scanning for the string encoding above (4-aligned
length word, NUL-terminated, valid UTF-8 containing a non-ASCII character
and no control characters other than newline or code points U+0100..U+1FFF,
zero padding). The last two filters only exist to reject a handful of
hash/float words that happen to look like a string (one in windowdataMain). Only those strings go in the worksheet; ASCII strings (widget
and texture ids such as kihon_center, tex_01, <I=61>) are left untouched.
The worksheet has one entry per DISTINCT text (the same widget text is
repeated many times); "count" is the number of occurrences, and build replaces
every occurrence.

Usage:
  wtd.py info FILE
  wtd.py dump FILE                 (list every non-ASCII string occurrence)
  wtd.py extract FILE OUT.json
  wtd.py build ORIGINAL IN.json OUT
  wtd.py roundtrip PATH...         (files or directories; PASS/FAIL each)
  wtd.py selftest FILE             (lengthen strings, rebuild, re-parse)
  wtd.py audit FILE                (evidence that SIZE is the only length-dependent field)
"""
import json
import os
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MAX_STR = 0x10000


def u32(d, o):
    return struct.unpack(">I", d[o:o + 4])[0]


def u16(d, o):
    return struct.unpack(">H", d[o:o + 2])[0]


def pad4(n):
    return (-n) % 4


def enc(s):
    return s.encode("utf-8") + b"\0"


def padded(n_bytes_with_nul):
    """Total encoded size of a string with this length word."""
    return 4 + n_bytes_with_nul + pad4(n_bytes_with_nul)


# ---------------------------------------------------------------- parsing

def read_marker(d, pos, what):
    if u16(d, pos) != 0xFFFF:
        raise ValueError("%s: expected 0xFFFF marker at 0x%X" % (what, pos))
    return u16(d, pos + 2), pos + 4


def parse(d):
    """Parse the container skeleton. Returns a dict; raises ValueError."""
    if d[:4] != b"_DTW":
        raise ValueError("not a _DTW file")
    p = {"version": u32(d, 4)}
    pos = 8
    n, pos = read_marker(d, pos, "textures")
    p["tex_off"] = pos - 4
    tex = []
    for _ in range(n):
        L = u32(d, pos)
        pos += 4
        if L == 0:
            tex.append("")
            continue
        raw = d[pos:pos + L]
        if raw[-1:] != b"\0":
            raise ValueError("texture name not NUL-terminated at 0x%X" % pos)
        tex.append(raw[:-1].decode("utf-8"))
        pos += L
        if d[pos:pos + pad4(L)] != bytes(pad4(L)):
            raise ValueError("non-zero string padding at 0x%X" % pos)
        pos += pad4(L)
    p["textures"] = tex
    n, pos = read_marker(d, pos, "palette")
    p["pal_off"], p["pal_n"] = pos - 4, n
    pos += 8 * n
    n, pos = read_marker(d, pos, "anims")
    p["anim_off"], p["anim_n"] = pos - 4, n
    for _ in range(n):
        k, total = u16(d, pos), u16(d, pos + 2)
        pos += 4
        s = 0
        for _ in range(k):
            s += u16(d, pos + 2)
            pos += 4
        if s != total:
            raise ValueError("anim table total mismatch at 0x%X" % pos)
    n, pos = read_marker(d, pos, "elements")
    p["el_off"], p["el_n"] = pos - 4, n
    els = []
    for _ in range(n):
        if pos % 4:
            raise ValueError("element not 4-aligned at 0x%X" % pos)
        size = u32(d, pos)
        if size < 8 or pos + size > len(d):
            raise ValueError("bad element size 0x%X at 0x%X" % (size, pos))
        els.append((pos, size))
        pos += size
    if pos != len(d):
        raise ValueError("element chain ends at 0x%X, file is 0x%X bytes" % (pos, len(d)))
    p["elements"] = els
    return p


def find_strings(d, start, end):
    """Non-ASCII strings in d[start:end] (start 4-aligned): list of
    (offset, text, length_word). Greedy left to right."""
    out = []
    pos = start
    while pos + 8 <= end:
        L = u32(d, pos)
        if 2 <= L <= MAX_STR and pos + 4 + L <= end:
            raw = d[pos + 4:pos + 4 + L]
            if raw[-1] == 0 and 0 not in raw[:-1] and max(raw) >= 0x80:
                try:
                    s = raw[:-1].decode("utf-8")
                except UnicodeDecodeError:
                    s = None
                if s is not None and all(
                        c == "\n" or not (ord(c) < 0x20 or 0x7F <= ord(c) < 0xA0
                                          or 0x100 <= ord(c) < 0x2000) for c in s):
                    e = pos + 4 + L
                    if e + pad4(L) <= end and d[e:e + pad4(L)] == bytes(pad4(L)):
                        out.append((pos, s, L))
                        pos = e + pad4(L)
                        continue
        pos += 4
    return out


def scan(d):
    """Returns (parse dict, per-element list of strings)."""
    p = parse(d)
    per = []
    for start, size in p["elements"]:
        per.append(find_strings(d, start + 4, start + size))
    return p, per


# ---------------------------------------------------------------- extract / build

def extract(path):
    d = open(path, "rb").read()
    p, per = scan(d)
    order, info = [], {}
    total = 0
    for strs in per:
        for off, s, L in strs:
            total += 1
            if s not in info:
                info[s] = {"count": 0, "first": off}
                order.append(s)
            info[s]["count"] += 1
    entries = []
    for i, s in enumerate(order):
        e = {"id": i, "jp": s, "en": ""}
        e["count"] = info[s]["count"]
        entries.append(e)
    return {
        "file": os.path.basename(path),
        "format": "WTD",
        "occurrences": total,
        "untouched": "ASCII-only strings (widget/texture ids, <I=n> tags) and all non-text data",
        "strings": entries,
    }


def build(orig_path, ws):
    d = open(orig_path, "rb").read()
    if ws.get("format") != "WTD":
        raise ValueError("worksheet format %r is not WTD" % ws.get("format"))
    p, per = scan(d)
    known = {}
    for strs in per:
        for off, s, L in strs:
            known[s] = True
    repl = {}
    for e in ws["strings"]:
        jp = e["jp"]
        if jp not in known:
            raise ValueError("worksheet string id %s not found in file: %r" % (e.get("id"), jp[:30]))
        en = e.get("en") or jp
        if "\0" in en:
            raise ValueError("NUL in translation id %s" % e.get("id"))
        repl[jp] = en
    out = bytearray(d[:p["elements"][0][0]])
    placed = []                                  # (offset in output, encoded string)
    for (start, size), strs in zip(p["elements"], per):
        base = len(out)
        body = bytearray()
        pos = start
        for off, s, L in strs:
            body += d[pos:off]
            new = enc(repl.get(s, s))
            placed.append((base + len(body), new))
            body += struct.pack(">I", len(new)) + new + bytes(pad4(len(new)))
            pos = off + padded(L)
        body += d[pos:start + size]
        if len(body) % 4:
            raise ValueError("internal: element body not 4-aligned")
        struct.pack_into(">I", body, 0, len(body))
        out += body
    out = bytes(out)
    check(out, p, placed)
    return out


def check(out, p0, placed):
    """Re-parse the built file end to end: header sections identical, element
    chain tiles the file to EOF, and every string sits where it was placed."""
    p1 = parse(out)
    if p1["el_n"] != p0["el_n"] or p1["textures"] != p0["textures"]:
        raise ValueError("re-parse: section counts changed")
    for off, new in placed:
        L = u32(out, off)
        if L != len(new) or out[off + 4:off + 4 + L] != new or                 out[off + 4 + L:off + 4 + L + pad4(L)] != bytes(pad4(L)):
            raise ValueError("re-parse: string at 0x%X is malformed" % off)


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
                    if f.lower().endswith(".wtd"):
                        yield os.path.join(root, f)
        else:
            yield path


def roundtrip(paths):
    ok = bad = 0
    for path in iter_files(paths):
        try:
            ws = extract(path)
            out = build(path, ws)
            orig = open(path, "rb").read()
            if out == orig:
                print("PASS %s (%d distinct strings)" % (path, len(ws["strings"])))
                ok += 1
            else:
                print("FAIL %s: first diff at 0x%X (sizes %d vs %d)" % (
                    path, first_diff(out, orig), len(out), len(orig)))
                bad += 1
        except Exception as e:  # noqa
            print("FAIL %s: %s" % (path, e))
            bad += 1
    print("roundtrip: %d pass, %d fail" % (ok, bad))
    return bad == 0


def selftest(path):
    """Lengthen strings by varying amounts, rebuild, re-parse and compare."""
    d = open(path, "rb").read()
    ws = extract(path)
    ents = ws["strings"]
    for i, e in enumerate(ents):
        # +1..+9 characters (3 bytes each) so every alignment case occurs
        e["en"] = e["jp"] + "あ" * (1 + i % 9)
    out = build(path, ws)
    p0, per0 = scan(d)
    p1, per1 = scan(out)
    assert p1["el_n"] == p0["el_n"] and p1["textures"] == p0["textures"]
    s0 = [s for strs in per0 for _, s, _ in strs]
    s1 = [s for strs in per1 for _, s, _ in strs]
    m = {e["jp"]: e["en"] for e in ents}
    assert s1 == [m[s] for s in s0], "string sequence differs"
    # everything outside the strings is byte-identical (element sizes aside)
    def cut(buf, p, per):
        res = []
        for (start, size), strs in zip(p["elements"], per):
            parts, pos = [], start + 4
            for off, s, L in strs:
                parts.append(buf[pos:off])
                pos = off + padded(L)
            parts.append(buf[pos:start + size])
            res.append(b"|".join(parts))
        return res
    assert cut(d, p0, per0) == cut(out, p1, per1), "non-string bytes changed"
    h = p0["elements"][0][0]
    assert out[:h] == d[:h], "header sections changed"
    # every element size must equal its new extent (chain verified by parse)
    grew = len(out) - len(d)
    changed = sum(1 for (a, s0_), (b, s1_) in zip(p0["elements"], p1["elements"]) if s0_ != s1_)
    print("selftest PASS %s: %d distinct strings lengthened, file %d -> %d bytes (+%d), "
          "%d of %d element sizes changed, chain re-parsed to EOF" % (
              os.path.basename(path), len(ents), len(d), len(out), grew, changed, p1["el_n"]))
    return True


def audit(path):
    """Re-derive the evidence for the 'only the element SIZE changes' claim."""
    d = open(path, "rb").read()
    p, per = scan(d)
    els = p["elements"]
    n = len(d)
    print("1. element chain: %d elements, sizes tile 0x%X..0x%X exactly" % (
        len(els), els[0][0], n))
    # 2. class-size words: [S][id][T] followed by the fixed 'object tail'
    #    (-1, 1, 0 x5, -1, 0) at word 7..15; S must be a function of
    #    (T, count word, kind word) alone, whatever string follows.
    tail = {7: 0xFFFFFFFF, 8: 1, 9: 0, 10: 0, 11: 0, 12: 0, 13: 0, 14: 0xFFFFFFFF, 15: 0}
    groups = {}
    for pos in range(0, n - 80, 4):
        if all(u32(d, pos + 4 * i) == v for i, v in tail.items()):
            groups.setdefault((u32(d, pos + 8), u32(d, pos + 64), u32(d, pos + 68)), []).append(pos)
    amb = vary = 0
    for k, hs in groups.items():
        if len({u32(d, h) for h in hs}) > 1:
            amb += 1
        if len({u32(d, h + 72) for h in hs if 1 <= u32(d, h + 72) <= 64}) > 1:
            vary += 1
    print("2. %d objects in %d classes; classes where the size word differs: %d; "
          "classes whose following string length varies: %d" % (
              sum(len(v) for v in groups.values()), len(groups), amb, vary))
    # 3. absolute offsets: any 4-aligned word equal to an element start/end?
    marks = {a for a, _ in els} | {a + s for a, s in els}
    hits = [o for o in range(0, n - 4, 4) if u32(d, o) in marks and u32(d, o) >= 0x100]
    print("3. 4-aligned words equal to an element start/end offset: %d %s" % (
        len(hits), ["0x%X" % h for h in hits[:6]]))
    # 4. size words inside element bodies equal to the distance to the element end
    cnt = 0
    for a, s in els:
        for o in range(a + 4, a + s - 3, 4):
            if u32(d, o) == a + s - o and u32(d, o) > 0x10:
                cnt += 1
    print("4. non-leading words equal to the distance to their element's end: %d "
          "(class sizes such as 0x40/0x140 that coincide)" % cnt)


def cmd_info(path):
    d = open(path, "rb").read()
    p, per = scan(d)
    print("%s: %d bytes, magic _DTW, word@4 = 0x%X" % (path, len(d), p["version"]))
    print("  textures  @0x%X  %d slots, %d named: %s" % (
        p["tex_off"], len(p["textures"]), sum(1 for t in p["textures"] if t),
        ", ".join(t for t in p["textures"] if t)[:80]))
    print("  palette   @0x%X  %d quads" % (p["pal_off"], p["pal_n"]))
    print("  anims     @0x%X  %d tables" % (p["anim_off"], p["anim_n"]))
    print("  elements  @0x%X  %d, chain ends exactly at EOF" % (p["el_off"], p["el_n"]))
    occ = sum(len(s) for s in per)
    dist = len({s for strs in per for _, s, _ in strs})
    print("  non-ASCII strings: %d occurrences, %d distinct, in %d elements" % (
        occ, dist, sum(1 for s in per if s)))
    big = sorted(p["elements"], key=lambda e: -e[1])[:3]
    print("  largest elements: " + ", ".join("0x%X (0x%X bytes)" % e for e in big))


def cmd_dump(path):
    d = open(path, "rb").read()
    p, per = scan(d)
    for i, strs in enumerate(per):
        for off, s, L in strs:
            print("el%03d 0x%06X  %s" % (i, off, s.replace("\n", "\\n")))


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "info" and len(argv) > 2:
        cmd_info(argv[2])
    elif cmd == "dump" and len(argv) > 2:
        cmd_dump(argv[2])
    elif cmd == "extract" and len(argv) > 3:
        ws = extract(argv[2])
        os.makedirs(os.path.dirname(os.path.abspath(argv[3])), exist_ok=True)
        with open(argv[3], "w", encoding="utf-8", newline="\n") as f:
            json.dump(ws, f, ensure_ascii=False, indent=1)
        print("%s: %d distinct strings (%d occurrences)" % (
            ws["file"], len(ws["strings"]), ws["occurrences"]))
    elif cmd == "build" and len(argv) > 4:
        ws = json.load(open(argv[3], encoding="utf-8"))
        out = build(argv[2], ws)
        open(argv[4], "wb").write(out)
        print("wrote %s (%d bytes)" % (argv[4], len(out)))
    elif cmd == "roundtrip" and len(argv) > 2:
        return 0 if roundtrip(argv[2:]) else 1
    elif cmd == "audit" and len(argv) > 2:
        audit(argv[2])
    elif cmd == "selftest" and len(argv) > 2:
        return 0 if selftest(argv[2]) else 1
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
