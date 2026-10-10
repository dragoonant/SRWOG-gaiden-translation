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

The body of an element is decoded in full by parse_element() (see
docs/formats-csb-wtd.md 2.2): element header + state lists, then groups of
objects, each object a list of flag-driven "part" records (bit n of the kind
word = field n present); display text is the bit-8 string of a part. extract/
build do not depend on that grammar: they find text by scanning for the string
encoding above (4-aligned
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
  wtd.py geometry FILE OUT.json    (per worksheet string: x, y, font w/h, align, element ...)
  wtd.py tree FILE [ELEMENT]       (decoded element bodies: groups, objects, part records)
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
    return apply_font_px(out, ws)


def apply_font_px(out, ws):
    """Per-string font size override: a worksheet entry with "font_px": N
    gets every occurrence's glyph cell w/h fields (f32, px of the 32 px
    font; 26 = the usual 0.8125 scale) set to N. Occurrences whose own
    record has no w/h inherit them from the object's base part; that base
    part is patched instead (it then applies to the whole object). The
    text parts are found by their (already translated) text."""
    want = {}        # text -> (px for every element, {element index: px})
    for e in ws["strings"]:
        px, per_el = e.get("font_px"), e.get("font_px_el") or {}
        if px or per_el:
            want[e.get("en") or e["jp"]] = (float(px) if px else None, {int(k): float(v) for k, v in per_el.items()})
    if not want:
        return out
    out = bytearray(out)
    _, tree = parse_tree(bytes(out))
    n = 0
    for ei, el in enumerate(tree):
        if isinstance(el, BodyError):
            continue
        for g in el["groups"]:
            for ob in g["objects"]:
                base = ob["parts"][0] if ob["parts"] else None
                for pt in ob["parts"]:
                    if pt.get("text") not in want:
                        continue
                    px, per_el = want[pt["text"]]
                    px = per_el.get(ei, px)
                    if px is None:
                        continue
                    src = pt if "w" in pt else base
                    if src is None or "w" not in src:
                        continue
                    for nm in ("w", "h"):
                        if nm in src["field_off"]:
                            struct.pack_into(">f", out, src["field_off"][nm], px)
                    n += 1
    return bytes(out)


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



# ---------------------------------------------------------------- element bodies

def f32(d, o):
    return struct.unpack(">f", d[o:o + 4])[0]


class BodyError(ValueError):
    pass


def read_str(d, o, end):
    """String at o (u32 len incl NUL + bytes + pad). Returns (text, next)."""
    L = u32(d, o)
    if L == 0:
        return "", o + 4
    if L > MAX_STR or o + 4 + L > end or d[o + 4 + L - 1] != 0:
        raise BodyError("bad string at 0x%X" % o)
    e = o + padded(L)
    if d[o + 4 + L:e] != bytes(e - o - 4 - L):
        raise BodyError("bad string padding at 0x%X" % o)
    return d[o + 4:o + 4 + L - 1].decode("utf-8", "replace"), e


# Part record: u32 kind, then one field per set bit of kind, in THIS order
# (not bit order).  type: str = string, f = f32, u = u32, u2 = 2 x u32,
# blob = u32 n + n bytes padded to 4.  Bits 3 and 4 share one colour word
# (u16 unknown 36000/18000/9000, u16 palette index).
PART_FIELDS = [
    (17, "s17", "str"),      # always "" where seen
    (0, "name", "str"),      # sprite/part name: kihon_center, page, center2_2 ...
    (1, "x", "f"),           # position, px right of the group origin
    (14, "y", "f"),          # position, px down from the group origin
    (2, "w", "f"),           # text: glyph cell width px (32 = 1.0); sprite: x scale
    (15, "h", "f"),          # text: glyph cell height px; sprite: y scale
    (3, "col", "u"),         # colour word (shared with bit 4)
    (4, "col", "u"),
    (5, "u5", "u2"),         # unknown pair
    (18, "u18", "u"),        # unknown word (0x00030000, 0xFFFE0000, 0 ...)
    (6, "link", "u"),        # s16/u16 pair: FFFF NNNN = element index, -1 = none
    (12, "hash", "u"),       # id hash (dynamic text source / referenced widget)
    (8, "text", "str"),      # display text
    (9, "flags", "u"),       # byte0: h-align 0 left / 1 centre / 2 right (+0x10/0x20);
                             # byte1: style bits 0x80/0x10/..; byte2: 0x10/0x20
    (10, "u10", "u"),        # small int (1, 4, 17, 384, 400)
    (11, "b11", "blob"),     # u32 size + value (size 4 -> 0x1A/0x1C, size 1 -> 0, size 0)
    (16, "label", "str"),    # widget id string ("135", "30011", "")
]
KNOWN_BITS = sum(1 << b for b, _, _ in PART_FIELDS)


def parse_part(d, o, end):
    kind = u32(d, o)
    start = o
    o += 4
    if kind & ~KNOWN_BITS:
        raise BodyError("unknown part kind bits 0x%X at 0x%X" % (kind, start))
    f = {"off": start, "kind": kind, "field_off": {}}
    for bit, nm, t in PART_FIELDS:
        if not kind & (1 << bit) or (bit == 4 and kind & 8):
            continue
        f["field_off"][nm] = o
        if t == "str":
            f[nm], o = read_str(d, o, end)
        elif t == "f":
            f[nm] = f32(d, o)
            o += 4
        elif t == "u":
            f[nm] = u32(d, o)
            o += 4
        elif t == "u2":
            f[nm] = (u32(d, o), u32(d, o + 4))
            o += 8
        else:
            n = u32(d, o)
            o += 4
            if n > 64:
                raise BodyError("blob size %d at 0x%X" % (n, o - 4))
            f[nm] = d[o:o + n]
            o += 4 * ((n + 3) // 4)
        if o > end:
            raise BodyError("part overruns element at 0x%X" % o)
    return f, o


def parse_object(d, o, end):
    """u32 S (class size), u32 id, u32 T, 4 words, -1, string, 4 x (u32 n,
    n x (u32, u32)), -1, 0, u16 nIds, u16 nParts, nIds x u32, nParts x part."""
    if o + 60 > end or u32(d, o + 28) != 0xFFFFFFFF:
        raise BodyError("object header at 0x%X" % o)
    ob = {"off": o, "S": u32(d, o), "id": u32(d, o + 4), "T": u32(d, o + 8),
          "a": [u32(d, o + 12 + 4 * i) for i in range(4)]}
    ob["label"], q = read_str(d, o + 32, end)
    ob["lists"] = []
    for _ in range(4):
        n = u32(d, q)
        q += 4
        if n > 256:
            raise BodyError("object list count %d at 0x%X" % (n, q - 4))
        ob["lists"].append([(u32(d, q + 8 * i), u32(d, q + 8 * i + 4)) for i in range(n)])
        q += 8 * n
    if u32(d, q) != 0xFFFFFFFF or u32(d, q + 4) != 0:
        raise BodyError("object tail at 0x%X (object 0x%X)" % (q, o))
    nids, nparts = struct.unpack(">HH", d[q + 8:q + 12])
    q += 12
    if nids > 64 or nparts > 256:
        raise BodyError("object counts at 0x%X" % o)
    ob["ids"] = [u32(d, q + 4 * i) for i in range(nids)]
    q += 4 * nids
    ob["parts"] = []
    for _ in range(nparts):
        pt, q = parse_part(d, q, end)
        ob["parts"].append(pt)
    return ob, q


def parse_element(d, es, sz):
    """u32 SIZE, u32 id, u32 type, -1, u32, u16 nStates, u16 v,
    nStates x (u32 k, k x (u32 objectId, u32 partIndex)),
    then groups to the end: u32 id, u16 nObj, u16 1, f32 x, f32 y, 4 x 0, nObj objects."""
    end = es + sz
    el = {"off": es, "size": sz, "id": u32(d, es + 4), "type": u32(d, es + 8),
          "w4": u32(d, es + 16)}
    if u32(d, es + 12) != 0xFFFFFFFF:
        raise BodyError("element header at 0x%X" % es)
    nst, el["v5"] = struct.unpack(">HH", d[es + 20:es + 24])
    o = es + 24
    el["states"] = []
    for _ in range(nst):
        k = u32(d, o)
        o += 4
        if k > 1000:
            raise BodyError("state list at 0x%X" % o)
        el["states"].append([(u32(d, o + 8 * i), u32(d, o + 8 * i + 4)) for i in range(k)])
        o += 8 * k
    el["groups"] = []
    while o < end:
        g = {"off": o, "id": u32(d, o)}
        n, one = struct.unpack(">HH", d[o + 4:o + 8])
        if one != 1 or any(u32(d, o + 16 + 4 * i) for i in range(4)):
            raise BodyError("group header at 0x%X" % o)
        g["x"], g["y"] = f32(d, o + 8), f32(d, o + 12)
        o += 32
        g["objects"] = []
        for _ in range(n):
            ob, o = parse_object(d, o, end)
            g["objects"].append(ob)
        el["groups"].append(g)
    if o != end:
        raise BodyError("element 0x%X does not tile to its end" % es)
    return el


def parse_tree(d):
    """(parse dict, list of decoded elements or BodyError per element)."""
    p = parse(d)
    out = []
    for es, sz in p["elements"]:
        try:
            out.append(parse_element(d, es, sz))
        except BodyError as e:
            out.append(e)
    return p, out


def align_of(flags):
    if flags is None:
        return "left"
    return {0: "left", 1: "center", 2: "right"}.get((flags >> 24) & 0xF)


def geometry(path):
    """Worksheet-shaped geometry: one entry per distinct text with every
    occurrence's position, font cell size, alignment and field offsets."""
    d = open(path, "rb").read()
    ws = extract(path)
    p, tree = parse_tree(d)
    by_off = {}
    for ei, el in enumerate(tree):
        if isinstance(el, BodyError):
            continue
        for gi, g in enumerate(el["groups"]):
            for oi, ob in enumerate(g["objects"]):
                for pi, pt in enumerate(ob["parts"]):
                    if "text" in pt:
                        by_off[pt["field_off"]["text"]] = (ei, gi, oi, pi, el, g, ob, pt)
    occ = {}
    _, per = scan(d)
    for ei, strs in enumerate(per):
        for off, s, L in strs:
            occ.setdefault(s, []).append((off, ei))
    for e in ws["strings"]:
        e["occurrences"] = []
        for off, ei in occ[e["jp"]]:
            if off not in by_off:
                e["occurrences"].append({"element": ei, "offset": "0x%X" % off, "confidence": "none",
                                         "note": "element body not decoded"})
                continue
            e["occurrences"].append(occurrence(d, by_off[off]))
        first = e["occurrences"][0]
        for k in ("x", "y", "w", "h", "scale", "align", "element", "confidence"):
            e[k] = first.get(k)
    ws["geometry"] = {
        "units": "layout px, 1:1 with the 1280x720 screen (inferred); x right / y down from the "
                 "group origin (group_x/group_y included in x/y); the window's own screen "
                 "position is set by code and is not in the file",
        "w_h": "glyph cell size in px of the 32 px font (26 = default 0.8125 scale); the text "
               "has no separate box field - text_w = chars x w, room = px to the next part on "
               "the same row (null = nothing to the right in this group)",
        "fields_at": "w/h/flags offsets are absolute file offsets of the f32/u32 in THIS "
                     "file (they move when build changes string lengths; re-run geometry on "
                     "the built file or address them by element/group/object/part path)",
        "align": "flags byte 0 (bits 24-25): 0 left, 1 center, 2 right (inferred from layouts)",
        "confidence": "high = own record has x, y, w, h; medium = some fields inherited from "
                      "the object's base record (part 0); low = font size not in file "
                      "(renderer default)",
    }
    return ws


def occurrence(d, hit):
    ei, gi, oi, pi, el, g, ob, pt = hit
    base = ob["parts"][0]
    o = {"element": ei, "group": gi, "object": oi, "part": pi, "offset": "0x%X" % pt["off"],
         "kind": "0x%X" % pt["kind"], "name": pt.get("name", base.get("name")),
         "group_x": g["x"], "group_y": g["y"], "inherited": []}
    for nm in ("x", "y", "w", "h", "flags", "col", "label"):
        src = pt if nm in pt else (base if nm in base else None)
        if src is None:
            o[nm] = None
            continue
        o[nm] = src[nm]
        if src is base and pt is not base:
            o["inherited"].append(nm)
        if nm in ("w", "h", "flags"):
            o[nm + "_offset"] = "0x%X" % src["field_off"][nm]
    o["x"] = (o["x"] or 0.0) + g["x"]
    o["y"] = (o["y"] or 0.0) + g["y"]
    o["scale"] = round(o["w"] / 32.0, 4) if o["w"] else None
    o["align"] = align_of(o["flags"])
    if o["flags"] is not None:
        o["flags"] = "0x%08X" % o["flags"]
    if o["col"] is not None:
        o["col"] = "0x%08X" % o["col"]
    o["chars"] = len(pt["text"])
    o["text_w"] = round(o["chars"] * o["w"], 1) if o["w"] else None
    # room: nearest base record of another object in this group, same row, to the right
    room = None
    hh = max(o["h"] or 24.0, 20.0)
    for ob2 in g["objects"]:
        if ob2 is ob:
            continue
        b2 = ob2["parts"][0] if ob2["parts"] else None
        if not b2 or "x" not in b2:
            continue
        dx = g["x"] + b2["x"] - o["x"]
        if dx > 0 and abs(g["y"] + b2.get("y", 0.0) - o["y"]) < hh and (room is None or dx < room):
            room = dx
    o["room"] = room
    if o["w"] is None or o["h"] is None:
        o["confidence"] = "low"
    elif o["inherited"]:
        o["confidence"] = "medium"
    else:
        o["confidence"] = "high"
    return o


def cmd_tree(path, which=None):
    d = open(path, "rb").read()
    p, tree = parse_tree(d)
    bad = sum(1 for e in tree if isinstance(e, BodyError))
    print("%s: %d elements, %d decoded, %d failed" % (path, len(tree), len(tree) - bad, bad))
    for ei, el in enumerate(tree):
        if which is not None and ei != which:
            continue
        if isinstance(el, BodyError):
            print("el%d: FAILED %s" % (ei, el))
            continue
        if which is None:
            print("el%d @0x%X id=%08X type=%d states=%d groups=%d objects=%d" % (
                ei, el["off"], el["id"], el["type"], len(el["states"]), len(el["groups"]),
                sum(len(g["objects"]) for g in el["groups"])))
            continue
        print("el%d @0x%X id=%08X type=%d w4=0x%X v5=%d states=%s" % (
            ei, el["off"], el["id"], el["type"], el["w4"], el["v5"], [len(s) for s in el["states"]]))
        for gi, g in enumerate(el["groups"]):
            print(" group %d id=%08X pos=(%g,%g) objects=%d" % (gi, g["id"], g["x"], g["y"], len(g["objects"])))
            for oi, ob in enumerate(g["objects"]):
                print("  obj %d @0x%X S=0x%X T=%d a=%s label=%r lists=%s" % (
                    oi, ob["off"], ob["S"], ob["T"], ["0x%X" % v for v in ob["a"]], ob["label"],
                    [len(l) for l in ob["lists"]]))
                for pi, pt in enumerate(ob["parts"]):
                    items = []
                    for bit, nm, t in PART_FIELDS:
                        if nm not in pt or (nm == "col" and items and items[-1][0] == "col"):
                            continue
                        v = pt[nm]
                        if isinstance(v, float):
                            v = "%g" % v
                        elif isinstance(v, int):
                            v = "0x%X" % v
                        elif isinstance(v, bytes):
                            v = v.hex() or "''"
                        elif isinstance(v, tuple):
                            v = "(0x%X,0x%X)" % v
                        else:
                            v = repr(v[:20])
                        items.append((nm, v))
                    print("   part %d @0x%X kind=0x%X %s" % (pi, pt["off"], pt["kind"],
                                                             " ".join("%s=%s" % i for i in items)))


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
    elif cmd == "geometry" and len(argv) > 3:
        ws = geometry(argv[2])
        os.makedirs(os.path.dirname(os.path.abspath(argv[3])), exist_ok=True)
        with open(argv[3], "w", encoding="utf-8", newline="\n") as f:
            json.dump(ws, f, ensure_ascii=False, indent=1)
        conf = {}
        for e in ws["strings"]:
            conf[e["confidence"]] = conf.get(e["confidence"], 0) + 1
        print("%s: %d strings, confidence %s" % (ws["file"], len(ws["strings"]), conf))
    elif cmd == "tree" and len(argv) > 2:
        cmd_tree(argv[2], int(argv[3]) if len(argv) > 3 else None)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
