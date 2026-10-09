#!/usr/bin/env python3
"""BMD battle-message (battle quote) extract / build for 2nd SRW OG (BLJS10133).

Files: Battle/Dat/Battle/Message/NNN.bmd, one per pilot (NNN = pilot id).
All integers big-endian; text is UTF-8, NUL-terminated.  See
docs/formats-bmd.md for the full write-up.  Layout (confirmed on all 307 files):

  0x00  u16 version (0x0100)
  0x02  u16 n_groups      (A)   0x04 u16 n_entries (B)   0x06 u16 n_lines (C)
  0x08  group table   A x 12 bytes
          u16 type   0=situation 1/2/3/4/15=weapon-class (id = weapon id)
          u16 id     situation id (0..21, ...) or weapon id
          u16 zero
          u16 flag   0 for the base situations, 1 otherwise
          u16 count  number of entries        u16 first  index into entry table
  +12*A entry table   B x 16 bytes   (one "choice" = one or more lines in a row)
          u8  kind   0 plain, 1 vs-pilot, 2 vs-pilot(2), 3 support, 4 crew
                     conversation, 5 special
          u8  weight 100 normally (also 120/50/40/20/10) - inferred priority
          u16 count  number of lines           u16 first  index into line table
          u16 target condition pilot / unit id (0 = none)
          u16 c4, u16 c5, u16 c6, u16 c7      extra condition fields (raw)
  +16*B line table    C x 16 bytes
          u16 zero   u16 speaker (pilot id)   u16 face   u16 zero
          u16 voice_bank   u16 voice_id
          u16 name_off  pool offset of a speaker-name override, 0xFFFF = none
          u16 text_off  pool offset of the line text
  +16*C string pool   UTF-8 NUL-terminated strings, offsets relative to pool
        start; file is zero-padded to a multiple of 4.

The pool is addressed only through name_off / text_off (every pool string is
referenced by at least one line; identical texts are shared).  Rebuilding
keeps the pool order and the tables, recomputes both offset fields and the
end padding.  Padding bytes are always zero, so nothing has to be reused.

Usage:
  battle.py info      FILE.bmd
  battle.py dump      FILE.bmd
  battle.py extract   FILE.bmd OUT.json
  battle.py build     ORIGINAL.bmd IN.json OUT.bmd
  battle.py roundtrip DIR            extract+build every .bmd, PASS/FAIL each
  battle.py stats     DIR            total / unique string counts
"""
import json
import os
import struct
import sys

HDR = struct.Struct(">HHHH")
GROUP = struct.Struct(">HHHHHH")
ENTRY = struct.Struct(">BBHHHHHHH")
LINE = struct.Struct(">HHHHHHHH")
NO_NAME = 0xFFFF
VERSION = 0x0100

KIND_NAMES = {0: "plain", 1: "vs", 2: "vs2", 3: "support", 4: "crew", 5: "special"}
GROUP_TYPES = {0: "situation", 1: "weapon", 2: "weapon2", 3: "weapon3",
               4: "weapon4", 15: "weapon15"}


class BmdError(Exception):
    pass


class Bmd:
    """Parsed .bmd.  groups / entries / lines are lists of tuples (raw fields);
    pool is the raw pool bytes (without the end padding); strings is the list
    of (offset, text) in pool order."""

    def __init__(self, data, name=""):
        self.name = name
        if len(data) < 8:
            raise BmdError("file too short")
        self.version, a, b, c = HDR.unpack_from(data, 0)
        if self.version != VERSION:
            raise BmdError("unexpected version 0x%04x" % self.version)
        o = 8
        self.groups = [GROUP.unpack_from(data, o + 12 * i) for i in range(a)]
        o += 12 * a
        self.entries = [ENTRY.unpack_from(data, o + 16 * i) for i in range(b)]
        o += 16 * b
        self.lines = [LINE.unpack_from(data, o + 16 * i) for i in range(c)]
        o += 16 * c
        if o > len(data):
            raise BmdError("tables run past end of file")
        self.pool_off = o
        self.size = len(data)
        # structural checks
        pos = 0
        for g in self.groups:
            if g[5] != pos:
                raise BmdError("group first-index not contiguous")
            pos += g[4]
        if pos != b:
            raise BmdError("group counts do not sum to n_entries")
        pos = 0
        for e in self.entries:
            if e[3] != pos:
                raise BmdError("entry first-index not contiguous")
            pos += e[2]
        if pos != c:
            raise BmdError("entry counts do not sum to n_lines")
        # walk the pool: strings are packed back to back, no empty strings,
        # zero padding (0-3 bytes) at the end
        refs = set()
        for ln in self.lines:
            refs.add(ln[7])
            if ln[6] != NO_NAME:
                refs.add(ln[6])
        self.strings = []
        p = o
        while p < len(data):
            q = data.find(b"\0", p)
            if q < 0:
                raise BmdError("unterminated string at 0x%x" % p)
            if q == p:
                break
            self.strings.append((p - o, data[p:q].decode("utf-8")))
            p = q + 1
        self.pool = data[o:p]
        self.pad = data[p:]
        if len(self.pad) != (-p) % 4 or any(self.pad):
            raise BmdError("unexpected trailing bytes after pool")
        offs = set(s[0] for s in self.strings)
        if refs - offs:
            raise BmdError("line references non-string offset %s"
                           % sorted(hex(x) for x in refs - offs)[:3])
        self.unreferenced = sorted(offs - refs)

    # ---- helpers -----------------------------------------------------------
    def string_at(self, off):
        e = self.pool.index(b"\0", off)
        return self.pool[off:e].decode("utf-8")

    def refs_by_offset(self):
        """offset -> list of (line_index, field) where field is 'text' or 'name'."""
        d = {}
        for k, ln in enumerate(self.lines):
            d.setdefault(ln[7], []).append((k, "text"))
            if ln[6] != NO_NAME:
                d.setdefault(ln[6], []).append((k, "name"))
        return d

    def line_context(self):
        """line_index -> (entry_index, group_index)."""
        ctx = {}
        for gi, g in enumerate(self.groups):
            for ei in range(g[5], g[5] + g[4]):
                e = self.entries[ei]
                for li in range(e[3], e[3] + e[2]):
                    ctx[li] = (ei, gi)
        return ctx

    def serialize(self, pool):
        out = bytearray(HDR.pack(self.version, len(self.groups),
                                 len(self.entries), len(self.lines)))
        for g in self.groups:
            out += GROUP.pack(*g)
        for e in self.entries:
            out += ENTRY.pack(*e)
        for ln in self.lines:
            out += LINE.pack(*ln)
        out += pool
        out += bytes((-len(out)) % 4)
        return bytes(out)


def load(path):
    with open(path, "rb") as f:
        return Bmd(f.read(), os.path.basename(path))


# ---- extract ---------------------------------------------------------------

def extract(path):
    bmd = load(path)
    refs = bmd.refs_by_offset()
    ctx = bmd.line_context()
    strings = []
    for i, (off, text) in enumerate(bmd.strings):
        uses = []
        speakers = []
        roles = set()
        for li, field in refs.get(off, []):
            ln = bmd.lines[li]
            ei, gi = ctx[li]
            e = bmd.entries[ei]
            g = bmd.groups[gi]
            roles.add(field)
            if ln[1] not in speakers:
                speakers.append(ln[1])
            uses.append({
                "line": li, "field": field, "entry": ei,
                "group": [g[0], g[1]], "kind": e[0], "weight": e[1],
                "target": e[4], "speaker": ln[1], "face": ln[2],
                "voice": [ln[4], ln[5]],
            })
        strings.append({
            "id": i, "offset": off,
            "role": "+".join(sorted(roles)) if roles else "unreferenced",
            "speakers": speakers,
            "jp": text, "en": "",
            "refs": uses,
        })
    return {
        "file": bmd.name, "format": "BMD",
        "counts": {"groups": len(bmd.groups), "entries": len(bmd.entries),
                   "lines": len(bmd.lines), "strings": len(bmd.strings)},
        "strings": strings,
    }


# ---- build -----------------------------------------------------------------

def build(original_path, ws):
    bmd = load(original_path)
    strs = ws["strings"]
    if ws.get("format") != "BMD":
        raise BmdError("json is not a BMD extract")
    if len(strs) != len(bmd.strings):
        raise BmdError("json has %d strings, original has %d"
                       % (len(strs), len(bmd.strings)))
    pool = bytearray()
    remap = {}
    for (off, jp), s in zip(bmd.strings, strs):
        if s["jp"] != jp:
            raise BmdError("string %d: jp text does not match original"
                           % s["id"])
        text = s.get("en") or jp
        enc = text.encode("utf-8")
        if b"\0" in enc:
            raise BmdError("string %d contains NUL" % s["id"])
        remap[off] = len(pool)
        pool += enc + b"\0"
    if len(pool) > 0xFFFF:
        raise BmdError("pool too large (%d bytes, max 65535)" % len(pool))
    lines = []
    for ln in bmd.lines:
        ln = list(ln)
        ln[7] = remap[ln[7]]
        if ln[6] != NO_NAME:
            ln[6] = remap[ln[6]]
        lines.append(tuple(ln))
    bmd.lines = lines
    return bmd.serialize(bytes(pool))


# ---- reports ---------------------------------------------------------------

def info(path):
    bmd = load(path)
    a, b, c = len(bmd.groups), len(bmd.entries), len(bmd.lines)
    print("%s: %d bytes, version 0x%04x" % (bmd.name, bmd.size, bmd.version))
    print("  groups  %4d @ 0x%06x" % (a, 8))
    print("  entries %4d @ 0x%06x" % (b, 8 + 12 * a))
    print("  lines   %4d @ 0x%06x" % (c, 8 + 12 * a + 16 * b))
    print("  pool    %d bytes @ 0x%06x, %d strings, %d pad byte(s)"
          % (len(bmd.pool), bmd.pool_off, len(bmd.strings), len(bmd.pad)))
    if bmd.unreferenced:
        print("  unreferenced strings:", bmd.unreferenced)
    speakers = {}
    for ln in bmd.lines:
        speakers[ln[1]] = speakers.get(ln[1], 0) + 1
    print("  speakers:", ", ".join("%d(x%d)" % kv for kv in
                                   sorted(speakers.items(), key=lambda x: -x[1])))
    names = sum(1 for ln in bmd.lines if ln[6] != NO_NAME)
    if names:
        print("  lines with name override: %d" % names)
    print("  groups:")
    for g in bmd.groups:
        print("    type %2d (%s) id %5d flag %d: %3d entries from %d"
              % (g[0], GROUP_TYPES.get(g[0], "?"), g[1], g[3], g[4], g[5]))


def dump(path):
    ws = extract(path)
    print("%s: %d strings" % (ws["file"], len(ws["strings"])))
    for s in ws["strings"]:
        print("[%d] @0x%04x %s" % (s["id"], s["offset"], s["jp"]))
        for r in s["refs"]:
            print("      line %d %s: group %d/%d entry %d kind %d(%s) w%d "
                  "target %d speaker %d face %d voice %d/%d"
                  % (r["line"], r["field"], r["group"][0], r["group"][1],
                     r["entry"], r["kind"], KIND_NAMES.get(r["kind"], "?"),
                     r["weight"], r["target"], r["speaker"], r["face"],
                     r["voice"][0], r["voice"][1]))


def roundtrip(d):
    ok = True
    files = sorted(f for f in os.listdir(d) if f.lower().endswith(".bmd"))
    npass = 0
    for f in files:
        p = os.path.join(d, f)
        with open(p, "rb") as fh:
            orig = fh.read()
        try:
            ws = extract(p)
            ws = json.loads(json.dumps(ws, ensure_ascii=False))
            out = build(p, ws)
        except Exception as e:  # report and continue
            print("FAIL %s: %s" % (f, e))
            ok = False
            continue
        if out == orig:
            npass += 1
            print("PASS %s (%d bytes, %d strings)"
                  % (f, len(orig), len(ws["strings"])))
        else:
            ok = False
            n = min(len(out), len(orig))
            diff = next((i for i in range(n) if out[i] != orig[i]), n)
            print("FAIL %s: first difference at 0x%x (orig %d bytes, built %d)"
                  % (f, diff, len(orig), len(out)))
    print("%d/%d files round-trip byte-identically" % (npass, len(files)))
    return ok


def stats(d):
    files = sorted(f for f in os.listdir(d) if f.lower().endswith(".bmd"))
    total = 0
    lines = 0
    uniq = set()
    names = set()
    for f in files:
        bmd = load(os.path.join(d, f))
        total += len(bmd.strings)
        lines += len(bmd.lines)
        uniq.update(t for _, t in bmd.strings)
        for ln in bmd.lines:
            if ln[6] != NO_NAME:
                names.add(bmd.string_at(ln[6]))
    print("%d files, %d line records, %d pool strings, %d unique strings, "
          "%d unique name overrides" % (len(files), lines, total, len(uniq),
                                        len(names)))


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    try:
        if cmd == "info" and len(argv) == 3:
            info(argv[2])
        elif cmd == "dump" and len(argv) == 3:
            dump(argv[2])
        elif cmd == "extract" and len(argv) == 4:
            ws = extract(argv[2])
            with open(argv[3], "w", encoding="utf-8", newline="\n") as f:
                json.dump(ws, f, ensure_ascii=False, indent=1)
            print("%s: %d strings" % (ws["file"], len(ws["strings"])))
        elif cmd == "build" and len(argv) == 5:
            with open(argv[3], encoding="utf-8") as f:
                ws = json.load(f)
            out = build(argv[2], ws)
            with open(argv[4], "wb") as f:
                f.write(out)
            print("wrote %s (%d bytes)" % (argv[4], len(out)))
        elif cmd == "roundtrip" and len(argv) == 3:
            return 0 if roundtrip(argv[2]) else 1
        elif cmd == "stats" and len(argv) == 3:
            stats(argv[2])
        else:
            print(__doc__)
            return 2
    except BmdError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv))
