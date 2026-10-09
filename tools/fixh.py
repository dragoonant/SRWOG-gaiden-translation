#!/usr/bin/env python3
"""fixh.py - FIXH fixed-data container tool (2nd Super Robot Wars OG, BLJS10133).

Files: Logic/Dat/FixedData/*.dat (26 files). Everything is big-endian.

Layout (see docs/formats-fixh.md for the full write-up):

    "FIXH" u32 8  u32 0xFEFF0000  u32 0x00010000       16-byte file header
    DOFS u32 size            u32[size/4]               id -> record index (0xFFFFFFFF = no record); optional
    DATA u32 size u32 count  count fixed-size records  size = count * record_size
    SOFS u32 size            u32[size/4]               byte offset of each string entry inside STRI payload
    STRI u32 size u32 count  string entries, payload padded with NUL to a multiple of 4 bytes

String entry:  u16 line_count, line_count x {u16 char_count, u16 byte_offset}, then the
               UTF-8 lines, each NUL-terminated, packed back to back.  byte_offset is relative
               to the first text byte (entry + 2 + 4*line_count); char_count counts Unicode
               code points.

Records reference strings by index (u8 or u16 fields, see FIELD_MAP).  No file stores text
inline in DATA; INLINE_FIELDS exists so that such a file could be handled if one turns up.

Usage:
    python -I fixh.py info FILE
    python -I fixh.py dump FILE
    python -I fixh.py extract FILE OUT.json
    python -I fixh.py build ORIGINAL.dat IN.json OUT.dat
    python -I fixh.py roundtrip DIR
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys

MAGIC = b"FIXH"
HEADER = MAGIC + struct.pack(">III", 8, 0xFEFF0000, 0x00010000)
COUNTED = ("DATA", "STRI")          # sections whose header carries a u32 count after the size
KNOWN = ("DOFS", "DATA", "SOFS", "STRI")
NO_RECORD = 0xFFFFFFFF

# ---------------------------------------------------------------------------
# Per-file knowledge: which record fields hold string indices.
# (offset_in_record, width_in_bytes, label, kind)
#   kind: "display"  - text the game shows
#         "comment"  - developer note, never shown (inferred from content)
#         "internal" - identifier / path, not shown
#         "unknown"  - role not established
# ---------------------------------------------------------------------------
def _keyguide_fields():
    f = []
    for k in range(12):
        base = 4 + 8 * k
        f.append((base + 6, 1, f"slot{k}_short", "display"))
        f.append((base + 7, 1, f"slot{k}_long", "display"))
    return f

FIELD_MAP = {
    "ACEBonusData":        [(1, 1, "text_2line", "display"), (45, 1, "text_1line", "display")],
    "AbilityData":         [(1, 1, "name", "display"), (2, 1, "name_b", "display"), (10, 1, "desc", "display")],
    "AbilityElementData":  [(1, 1, "name", "display"), (54, 1, "desc", "display")],
    "AntiFieldTypeData":   [(1, 1, "name", "display")],
    "BGMData":             [(1, 1, "title", "display")],
    "HelpData":            [(2, 2, "text", "display")],
    "KeyGuideData":        _keyguide_fields(),
    "KeyWordData":         [(2, 1, "name", "display"), (3, 1, "name_b", "display"), (4, 1, "name_c", "display"), (5, 1, "desc", "display")],
    "MAXChangeBonusData":  [(1, 1, "name", "display"), (56, 1, "desc", "display")],
    "MapWeaponData":       [(2, 1, "grid", "display"), (3, 1, "type_label", "display")],
    "PartsData":           [(1, 1, "name", "display"), (62, 1, "desc", "display")],
    "PilotData":           [(2, 2, "name", "display"), (4, 2, "comment", "comment"), (12, 2, "fullname_2", "display"),
                            (14, 2, "fullname_1", "display"), (0x100, 2, "voice_actor", "display")],
    "PilotDictionaryData": [(2, 1, "text", "display")],
    "SkillData":           [(1, 1, "name", "display"), (28, 1, "desc", "display")],
    "SpecialEffectData":   [(1, 1, "name", "display")],
    "SpiritData":          [(1, 1, "name", "display"), (10, 1, "desc", "display")],
    "StageData":           [(2, 1, "title", "display"), (3, 1, "subtitle", "display"), (4, 1, "title_b", "unknown"),
                            (5, 1, "route", "display"), (13, 1, "icon", "internal")],
    "TrophyData":          [(4, 1, "name", "display"), (5, 1, "desc", "display"), (6, 1, "internal_id", "internal"), (10, 1, "image", "internal")],
    "UnitData":            [(2, 2, "name", "display"), (4, 2, "comment", "comment"), (0xA8, 2, "height", "display"), (0xAA, 2, "weight", "display")],
    "UnitDictionaryData":  [(2, 1, "text", "display")],
    "WeaponData":          [(4, 2, "name", "display"), (6, 2, "comment", "comment")],
}

# Inline fixed-width UTF-8 text fields inside DATA records:
#   file stem -> [(offset_in_record, width_bytes, label)]
# None of the 26 BLJS10133 FixedData files has any (verified by scanning every DATA
# payload for multi-byte UTF-8 sequences).  The machinery is kept so a future file can
# be described here without code changes.
INLINE_FIELDS: dict[str, list[tuple[int, int, str]]] = {}


class FixhError(Exception):
    pass


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
class Section:
    __slots__ = ("magic", "hdr_off", "size", "count", "start")

    def __init__(self, magic, hdr_off, size, count, start):
        self.magic, self.hdr_off, self.size, self.count, self.start = magic, hdr_off, size, count, start

    @property
    def end(self):
        return self.start + self.size

    @property
    def has_count(self):
        return self.magic in COUNTED


class FixhFile:
    def __init__(self, data: bytes, name: str = ""):
        self.data = data
        self.name = name
        self.stem = os.path.splitext(os.path.basename(name))[0] if name else ""
        if data[:16] != HEADER:
            raise FixhError(f"{name}: bad FIXH header {data[:16].hex()}")
        self.sections: list[Section] = []
        o = 16
        while o < len(data):
            if o + 8 > len(data):
                raise FixhError(f"{name}: truncated section header at {o:#x}")
            magic = data[o:o + 4].decode("ascii", "replace")
            if magic not in KNOWN:
                raise FixhError(f"{name}: unknown section magic {magic!r} at {o:#x}")
            size = be32(data, o + 4)
            if magic in COUNTED:
                count = be32(data, o + 8)
                start = o + 12
            else:
                count = None
                start = o + 8
            if start + size > len(data):
                raise FixhError(f"{name}: section {magic} at {o:#x} overruns file")
            self.sections.append(Section(magic, o, size, count, start))
            o = start + size
        self.by_magic = {s.magic: s for s in self.sections}
        self._parse_tables()

    # -- tables -----------------------------------------------------------
    def _parse_tables(self):
        d = self.data
        self.dofs = []
        if "DOFS" in self.by_magic:
            s = self.by_magic["DOFS"]
            self.dofs = list(struct.unpack_from(f">{s.size // 4}I", d, s.start))
        self.record_size = 0
        self.records: list[bytes] = []
        if "DATA" in self.by_magic:
            s = self.by_magic["DATA"]
            if s.count:
                if s.size % s.count:
                    raise FixhError(f"{self.name}: DATA size {s.size:#x} not divisible by count {s.count}")
                self.record_size = s.size // s.count
                self.records = [d[s.start + i * self.record_size: s.start + (i + 1) * self.record_size]
                                for i in range(s.count)]
        self.sofs = []
        if "SOFS" in self.by_magic:
            s = self.by_magic["SOFS"]
            self.sofs = list(struct.unpack_from(f">{s.size // 4}I", d, s.start))
        self.strings: list[list[str]] = []
        self.string_offsets: list[int] = []     # absolute offset of each entry header
        self.string_text_offsets: list[int] = []  # absolute offset of first text byte
        if "STRI" in self.by_magic:
            s = self.by_magic["STRI"]
            if s.count != len(self.sofs):
                raise FixhError(f"{self.name}: STRI count {s.count} != SOFS entries {len(self.sofs)}")
            for i, rel in enumerate(self.sofs):
                a = s.start + rel
                n = be16(d, a)
                tb = a + 2 + 4 * n
                lines = []
                for k in range(n):
                    cc = be16(d, a + 2 + 4 * k)
                    off = be16(d, a + 4 + 4 * k)
                    e = d.index(b"\0", tb + off)
                    txt = d[tb + off:e].decode("utf-8")
                    if len(txt) != cc:
                        raise FixhError(f"{self.name}: string {i} line {k}: char count {cc} != {len(txt)}")
                    lines.append(txt)
                self.strings.append(lines)
                self.string_offsets.append(a)
                self.string_text_offsets.append(tb)

    # -- field map --------------------------------------------------------
    def fields(self):
        return FIELD_MAP.get(self.stem, [])

    def inline_fields(self):
        return INLINE_FIELDS.get(self.stem, [])

    def string_refs(self) -> list[list[tuple[int, str, str]]]:
        """For each string index: list of (record_index, field_label, kind) referencing it."""
        refs = [[] for _ in self.strings]
        n = len(self.strings)
        for ri, r in enumerate(self.records):
            for off, w, label, kind in self.fields():
                v = read_field(r, off, w)
                if v < n:
                    refs[v].append((ri, label, kind))
        return refs

    def record_id(self, ri: int) -> int | None:
        """Record id as used by DOFS, if the file has a DOFS table (u8 or u16 at offset 0)."""
        if not self.dofs or not self.records:
            return None
        r = self.records[ri]
        for w in (2, 1):
            v = read_field(r, 0, w)
            if v < len(self.dofs) and self.dofs[v] == ri:
                return v
        return None


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------
def encode_strings(strings: list[list[str]]) -> tuple[bytes, bytes]:
    """Return (sofs_payload, stri_payload) for the given list of line lists."""
    sofs = []
    out = bytearray()
    for i, lines in enumerate(strings):
        if not lines:
            raise FixhError(f"string {i}: an entry needs at least one line")
        sofs.append(len(out))
        texts = [l.encode("utf-8") + b"\0" for l in lines]
        hdr = bytearray(struct.pack(">H", len(lines)))
        pos = 0
        for k, (l, t) in enumerate(zip(lines, texts)):
            cc = len(l)
            if cc > 0xFFFF or pos > 0xFFFF:
                raise FixhError(f"string {i} line {k}: too long for u16 header fields")
            hdr += struct.pack(">HH", cc, pos)
            pos += len(t)
        out += hdr
        for t in texts:
            out += t
    while len(out) % 4:
        out.append(0)
    return struct.pack(f">{len(sofs)}I", *sofs), bytes(out)


def build_bytes(orig: FixhFile, strings: list[list[str]], inline: dict[tuple[int, str], str] | None = None) -> bytes:
    """Rebuild orig with the given strings (same count as original) and optional inline edits
    {(record_index, label): text}.  Everything else is copied byte for byte."""
    if "STRI" in orig.by_magic and len(strings) != len(orig.strings):
        raise FixhError(f"{orig.name}: string count {len(strings)} != original {len(orig.strings)} "
                        "(records reference strings by index; adding/removing is not supported)")
    records = [bytearray(r) for r in orig.records]
    if inline:
        fmap = {label: (off, w) for off, w, label in orig.inline_fields()}
        for (ri, label), text in inline.items():
            if label not in fmap:
                raise FixhError(f"{orig.name}: unknown inline field {label!r}")
            off, w = fmap[label]
            enc = text.encode("utf-8")
            if enc == orig.records[ri][off:off + w].split(b"\0", 1)[0]:
                continue  # unchanged: keep the original bytes (including any padding garbage)
            # Keep one byte for the NUL terminator unless the original field was already
            # completely filled (no terminator), so that an unmodified extract rebuilds identically.
            limit = w if b"\0" not in orig.records[ri][off:off + w] else w - 1
            if len(enc) > limit:
                raise FixhError(f"{orig.name}: record {ri} field {label}: {len(enc)} bytes does not fit "
                                f"in {w}-byte field (max {limit} bytes)")
            records[ri][off:off + w] = enc + b"\0" * (w - len(enc))
    sofs_payload, stri_payload = encode_strings(strings) if "STRI" in orig.by_magic else (b"", b"")
    out = bytearray(HEADER)
    for s in orig.sections:
        if s.magic == "DATA":
            payload = b"".join(records) if records else orig.data[s.start:s.end]
            out += b"DATA" + struct.pack(">II", len(payload), s.count)
        elif s.magic == "SOFS":
            payload = sofs_payload
            out += b"SOFS" + struct.pack(">I", len(payload))
        elif s.magic == "STRI":
            payload = stri_payload
            out += b"STRI" + struct.pack(">II", len(payload), len(strings))
        else:  # DOFS and anything else: verbatim
            payload = orig.data[s.start:s.end]
            out += s.magic.encode("ascii") + struct.pack(">I", len(payload))
        out += payload
    return bytes(out)


# ---------------------------------------------------------------------------
# Extract / JSON
# ---------------------------------------------------------------------------
def string_role(refs: list[tuple[int, str, str]]) -> str:
    """display wins over everything (the game shows it through at least one field), then
    unknown, internal, comment; orphan when no record references the string."""
    if not refs:
        return "orphan"
    kinds = {k for _, _, k in refs}
    for k in ("display", "unknown", "internal", "comment"):
        if k in kinds:
            return k
    return "mixed"


def extract_entries(f: FixhFile) -> dict:
    refs = f.string_refs()
    entries = []
    for i, lines in enumerate(f.strings):
        a = f.string_offsets[i]
        nxt = (f.by_magic["STRI"].start + f.sofs[i + 1]) if i + 1 < len(f.sofs) else None
        text_bytes = sum(len(l.encode("utf-8")) + 1 for l in lines)
        e = {
            "id": i,
            "section": "STRI",
            "offset": a,
            "text_offset": f.string_text_offsets[i],
            "role": string_role(refs[i]),
            "refs": [f"rec{ri}.{label}" for ri, label, _ in refs[i]],
            "orig_chars": [len(l) for l in lines],
            "orig_bytes": text_bytes,
            "budget": {
                "type": "variable",
                "note": "Variable-length; offsets are recomputed on build. Limits: 65535 code points per line, "
                        "65535 bytes of text per entry. No on-screen width limit is encoded in the file.",
            },
        }
        if len(lines) == 1 and "\n" not in lines[0]:
            e["text"] = lines[0]
        else:
            e["lines"] = lines
        e["en"] = ""
        entries.append(e)
    inline = []
    for ri, r in enumerate(f.records):
        for off, w, label in f.inline_fields():
            raw = r[off:off + w]
            try:
                txt = raw.split(b"\0", 1)[0].decode("utf-8")
            except UnicodeDecodeError as ex:
                raise FixhError(f"{f.name}: record {ri} inline field {label} is not UTF-8: {raw.hex()}") from ex
            limit = w if b"\0" not in raw else w - 1
            inline.append({
                "id": f"inline:rec{ri}:{label}",
                "section": "DATA",
                "offset": f.by_magic["DATA"].start + ri * f.record_size + off,
                "record": ri,
                "field": label,
                "role": "display",
                "budget": {"type": "fixed", "bytes": w, "max_text_bytes": limit,
                           "note": f"Inline fixed-width field of {w} bytes: at most {limit} UTF-8 bytes, zero padded."},
                "text": txt,
            })
    doc = {
        "file": os.path.basename(f.name),
        "format": "FIXH 1.0 big-endian",
        "sections": [{"magic": s.magic, "header_offset": s.hdr_off, "payload_offset": s.start,
                      "size": s.size, "count": s.count} for s in f.sections],
        "records": {"count": len(f.records), "size": f.record_size},
        "dofs": {"entries": len(f.dofs), "unused_ids": sum(1 for v in f.dofs if v == NO_RECORD)} if f.dofs else None,
        "string_fields": [{"offset": off, "width": w, "label": label, "kind": kind} for off, w, label, kind in f.fields()],
        "notes": [
            "Put the English in 'en' (use a newline between lines). 'text'/'lines' hold the original and are used when 'en' is empty.",
            "Do not add or remove entries: records reference strings by index.",
            "role: display = shown in game; comment = developer note (never displayed, safe to leave untranslated); "
            "internal = identifier/path; orphan = referenced by no record; unknown = not established.",
        ],
        "strings": entries,
        "inline_strings": inline,
    }
    return doc


def strings_from_json(doc: dict, orig: FixhFile) -> tuple[list[list[str]], dict]:
    entries = doc.get("strings", [])
    strings: list[list[str] | None] = [None] * len(entries)
    for e in entries:
        i = e["id"]
        if not isinstance(i, int) or i < 0 or i >= len(entries) or strings[i] is not None:
            raise FixhError(f"bad or duplicate string id {i!r}")
        if e.get("en"):
            lines = e["en"].split("\n")   # English: newline separates lines
        elif "lines" in e:
            lines = list(e["lines"])
        elif "text" in e:
            lines = [e["text"]]
        else:
            raise FixhError(f"string {i}: neither 'text' nor 'lines'")
        if not all(isinstance(l, str) for l in lines):
            raise FixhError(f"string {i}: lines must be strings")
        strings[i] = lines
    inline = {}
    for e in doc.get("inline_strings", []):
        inline[(e["record"], e["field"])] = e["text"]
    return strings, inline  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def be32(b, o): return struct.unpack_from(">I", b, o)[0]
def be16(b, o): return struct.unpack_from(">H", b, o)[0]
def read_field(r, off, w): return r[off] if w == 1 else be16(r, off)


def load(path: str) -> FixhFile:
    with open(path, "rb") as fh:
        return FixhFile(fh.read(), path)


def read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_info(args):
    f = load(args.file)
    print(f"{f.name}: {len(f.data)} bytes ({len(f.data):#x})")
    print(f"  {'section':8}{'hdr':>8}{'payload':>9}{'size':>9}{'count':>7}  notes")
    for s in f.sections:
        note = ""
        if s.magic == "DATA" and s.count:
            note = f"record size {f.record_size} ({f.record_size:#x})"
        elif s.magic == "DOFS":
            unused = sum(1 for v in f.dofs if v == NO_RECORD)
            note = f"{len(f.dofs)} ids, {unused} unused (0xFFFFFFFF)"
        elif s.magic == "SOFS":
            note = f"{len(f.sofs)} offsets"
        elif s.magic == "STRI":
            nl = sum(len(x) for x in f.strings)
            pad = s.size - (sum(2 + 4 * len(x) + sum(len(l.encode('utf-8')) + 1 for l in x) for x in f.strings))
            note = f"{len(f.strings)} strings, {nl} lines, {pad} pad bytes"
        cnt = "" if s.count is None else str(s.count)
        print(f"  {s.magic:8}{s.hdr_off:>#8x}{s.start:>#9x}{s.size:>#9x}{cnt:>7}  {note}")
    fl = f.fields()
    if fl:
        print("  string-index fields in each record:")
        for off, w, label, kind in fl:
            print(f"    +{off:#04x} u{8 * w:<3} {label:14} {kind}")
    elif f.strings:
        print("  (no field map known for this file)")
    il = f.inline_fields()
    if il:
        print("  inline text fields:", ", ".join(f"+{o:#x}[{w}] {l}" for o, w, l in il))


def cmd_dump(args):
    f = load(args.file)
    refs = f.string_refs()
    for i, lines in enumerate(f.strings):
        role = string_role(refs[i])
        rs = ",".join(f"rec{ri}.{label}" for ri, label, _ in refs[i][:6]) or "-"
        if len(refs[i]) > 6:
            rs += f",(+{len(refs[i]) - 6} more)"
        nb = sum(len(l.encode("utf-8")) + 1 for l in lines)
        head = f"[{i}] @{f.string_offsets[i]:#x} lines={len(lines)} chars={sum(len(l) for l in lines)} bytes={nb} {role} refs={rs}"
        print(head)
        for l in lines:
            print("    " + l.replace("\n", "\\n"))
    for ri, r in enumerate(f.records):
        for off, w, label in f.inline_fields():
            txt = r[off:off + w].split(b"\0", 1)[0].decode("utf-8")
            print(f"[inline rec{ri}.{label}] @{f.by_magic['DATA'].start + ri * f.record_size + off:#x} width={w}")
            print("    " + txt)
    print(f"# {len(f.strings)} strings")


def cmd_extract(args):
    f = load(args.file)
    doc = extract_entries(f)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"{args.out}: {len(doc['strings'])} strings, {len(doc['inline_strings'])} inline fields")


def cmd_build(args):
    orig = load(args.original)
    doc = read_json(args.json)
    if doc.get("file") and doc["file"] != os.path.basename(args.original):
        print(f"warning: JSON is for {doc['file']}, original is {os.path.basename(args.original)}", file=sys.stderr)
    strings, inline = strings_from_json(doc, orig)
    out = build_bytes(orig, strings, inline)
    with open(args.out, "wb") as fh:
        fh.write(out)
    print(f"{args.out}: {len(out)} bytes ({'identical to' if out == orig.data else 'differs from'} original)")


def roundtrip_one(path: str) -> tuple[bool, str]:
    f = load(path)
    doc = json.loads(json.dumps(extract_entries(f), ensure_ascii=False))
    strings, inline = strings_from_json(doc, f)
    out = build_bytes(f, strings, inline)
    if out == f.data:
        return True, f"{len(f.strings)} strings"
    n = next((i for i in range(min(len(out), len(f.data))) if out[i] != f.data[i]), min(len(out), len(f.data)))
    return False, f"first difference at {n:#x} (rebuilt {len(out)} bytes, original {len(f.data)})"


def cmd_roundtrip(args):
    paths = sorted(p for p in (os.path.join(args.dir, n) for n in os.listdir(args.dir)) if p.lower().endswith(".dat"))
    fails = 0
    total = 0
    for p in paths:
        try:
            ok, msg = roundtrip_one(p)
        except Exception as ex:  # noqa: BLE001
            ok, msg = False, f"error: {ex}"
        if ok:
            total += int(msg.split()[0])
        fails += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {os.path.basename(p):26} {msg}")
    print(f"{len(paths) - fails}/{len(paths)} files pass, {total} strings")
    return 1 if fails else 0


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="FIXH fixed-data container tool")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info", help="print the section table"); p.add_argument("file"); p.set_defaults(fn=cmd_info)
    p = sub.add_parser("dump", help="print every string with index, offset and referencing fields"); p.add_argument("file"); p.set_defaults(fn=cmd_dump)
    p = sub.add_parser("extract", help="write strings to JSON"); p.add_argument("file"); p.add_argument("out"); p.set_defaults(fn=cmd_extract)
    p = sub.add_parser("build", help="rebuild a .dat from the original plus a JSON")
    p.add_argument("original"); p.add_argument("json"); p.add_argument("out"); p.set_defaults(fn=cmd_build)
    p = sub.add_parser("roundtrip", help="extract+build every .dat in DIR and compare"); p.add_argument("dir"); p.set_defaults(fn=cmd_roundtrip)
    args = ap.parse_args(argv)
    try:
        rc = args.fn(args)
    except FixhError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    return rc or 0


if __name__ == "__main__":
    sys.exit(main())
