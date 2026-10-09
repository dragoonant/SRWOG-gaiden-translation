#!/usr/bin/env python3
"""Inventory and patch the Japanese strings inside the decrypted EBOOT.elf.

The EBOOT is a big-endian ELF64 (PPC64, PS3). Strings live in the data
segments as NUL-terminated UTF-8. The PS3 ABI uses 32-bit pointers, so data
tables reference a string by its 32-bit virtual address stored as a
big-endian u32; code references it through lis/addi (or lis/ori) pairs.

Commands:
  extract EBOOT.elf OUT.json      every Japanese/full-width string with
                                  address, file offset, byte budget (the
                                  original NUL-terminated length) and the
                                  number of u32 data references found
  build   EBOOT.elf IN.json OUT.elf
                                  in-place replacement; refuses any "en"
                                  longer than the budget (relocation to a
                                  free area is Phase 2 work)
  dump    EBOOT.elf               print the strings
  roundtrip EBOOT.elf             extract + build with no changes, compare
"""
import json
import re
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JP = re.compile(r"[぀-ヿ一-鿿！-～　-〿]")
# ASCII plus the UTF-8 encodings of kana/CJK/full-width/general punctuation
STR = re.compile(
    rb"(?:[\x20-\x7e]|\xe3[\x80-\x83][\x80-\xbf]|[\xe4-\xe9][\x80-\xbf][\x80-\xbf]"
    rb"|\xef[\xbc-\xbf][\x80-\xbf]|\xe2[\x80-\xbf][\x80-\xbf]|\xc2[\xa0-\xbf]|\xc3[\x80-\xbf]"
    rb"|\n|\t){1,}\0")


def segments(elf):
    """Yield (vaddr, file_offset, filesz, flags) for PT_LOAD headers."""
    if elf[:4] != b"\x7fELF" or elf[4] != 2 or elf[5] != 2:
        raise ValueError("not a big-endian ELF64")
    phoff = struct.unpack_from(">Q", elf, 0x20)[0]
    phentsize, phnum = struct.unpack_from(">HH", elf, 0x36)
    for i in range(phnum):
        p = phoff + i * phentsize
        p_type, p_flags = struct.unpack_from(">II", elf, p)
        p_offset, p_vaddr, _p_paddr, p_filesz = struct.unpack_from(">QQQQ", elf, p + 8)
        if p_type == 1:
            yield p_vaddr, p_offset, p_filesz, p_flags


def off_to_va(segs, off):
    for va, fo, sz, _ in segs:
        if fo <= off < fo + sz:
            return va + (off - fo)
    return None


def find_strings(elf):
    segs = list(segments(elf))
    out = []
    for m in STR.finditer(elf):
        raw = m.group()[:-1]
        try:
            s = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        # Two Japanese code points, or one plus a NUL right before: filters
        # the random 3-byte sequences that code segments throw up.
        if len(JP.findall(s)) < 2 and not (m.start() > 0 and elf[m.start() - 1] == 0 and JP.search(s)):
            continue
        # Must start right after a NUL (or at a 4-byte boundary) to avoid
        # catching the tail of a longer non-Japanese string.
        start = m.start()
        if start > 0 and elf[start - 1] != 0 and start % 4:
            continue
        va = off_to_va(segs, start)
        if va is None:
            continue
        out.append({"offset": start, "va": va, "jp": s, "budget": len(raw)})
    return out


def count_refs(elf, strings):
    """Count big-endian u32 occurrences of each string's 32-bit address."""
    # Build a map from the u32 pattern to indices; scan the file once.
    want = {}
    for i, e in enumerate(strings):
        want.setdefault(struct.pack(">I", e["va"] & 0xFFFFFFFF), []).append(i)
    for e in strings:
        e["data_refs"] = 0
    for i in range(0, len(elf) - 3):
        hit = want.get(elf[i:i + 4])
        if hit:
            for k in hit:
                strings[k]["data_refs"] += 1
    return strings


def extract(path):
    elf = open(path, "rb").read()
    strings = count_refs(elf, find_strings(elf))
    # Drop unreferenced single-character hits outside the main data region.
    strings = [e for e in strings if e["data_refs"] or len(JP.findall(e["jp"])) >= 2]
    for i, e in enumerate(strings):
        e["id"] = i
        e["en"] = ""
    return {"file": "EBOOT.elf", "format": "ELF", "strings": strings}


def build(path, ws, out_path):
    elf = bytearray(open(path, "rb").read())
    changed = 0
    for e in ws["strings"]:
        en = e.get("en", "")
        if not en:
            continue
        b = en.encode("utf-8")
        if len(b) > e["budget"]:
            # Too long to replace in place: keep the Japanese so the build
            # still works, and say so (fitcheck reports these as "bytes").
            print("skipped string %d: %d bytes > budget %d: %r" % (e["id"], len(b), e["budget"], en))
            continue
        off = e["offset"]
        if elf[off:off + e["budget"]] != e["jp"].encode("utf-8"):
            raise ValueError("string %d: original bytes do not match at 0x%X" % (e["id"], off))
        elf[off:off + e["budget"] + 1] = b + bytes(e["budget"] + 1 - len(b))
        changed += 1
    open(out_path, "wb").write(bytes(elf))
    return changed


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "extract":
        ws = extract(argv[2])
        with open(argv[3], "w", encoding="utf-8", newline="\n") as f:
            json.dump(ws, f, ensure_ascii=False, indent=1)
        refs = sum(1 for e in ws["strings"] if e["data_refs"])
        print("%d strings, %d with at least one data reference" % (len(ws["strings"]), refs))
    elif cmd == "build":
        ws = json.load(open(argv[3], encoding="utf-8"))
        n = build(argv[2], ws, argv[4])
        print("wrote %s, %d strings replaced" % (argv[4], n))
    elif cmd == "dump":
        for e in extract(argv[2])["strings"]:
            print("%08X va=%08X refs=%d len=%3d %s" % (e["offset"], e["va"], e["data_refs"], e["budget"], e["jp"][:70]))
    elif cmd == "roundtrip":
        ws = extract(argv[2])
        tmp = argv[2] + ".rt"
        build(argv[2], ws, tmp)
        same = open(tmp, "rb").read() == open(argv[2], "rb").read()
        print("roundtrip:", "identical" if same else "DIFFERS", "(%d strings)" % len(ws["strings"]))
        return 0 if same else 1
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
