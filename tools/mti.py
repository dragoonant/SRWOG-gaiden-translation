#!/usr/bin/env python3
"""Map terrain info (General3d/Dat/Map/MapLandInfo/landinfo.mti).

Layout (confirmed by round trip):
  0x00 "MPTI"  u16 0xFEFF  u16 0x0001  u16 0  u16 0x0FA8 (?)
  0x0C 1024 records x 84 bytes:
       +0  char[64]  name, UTF-8, NUL-terminated, zero padded:
                     "<terrain>@<detail>", e.g. 森@バラルの園. The Map Data
                     panel shows the part before '@'; the detail is a
                     designer note (night/dark/no-entry/...).
       +64 20 bytes of terrain numbers (defense/evasion %, flags), untouched.
Only the 300 non-empty names are worksheet entries. English must fit in 63
bytes (UTF-8) including the '@' and detail.

Usage:
  mti.py extract FILE OUT.json | build ORIGINAL IN.json OUT | roundtrip FILE
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REC, NAME, HEADER, COUNT = 84, 64, 12, 1024


def parse(data):
    if data[:4] != b"MPTI" or len(data) != HEADER + REC * COUNT:
        raise ValueError("not a landinfo.mti of the expected size")
    names = []
    for i in range(COUNT):
        o = HEADER + i * REC
        names.append(data[o:o + NAME].split(b"\0")[0].decode("utf-8"))
    return names


def extract(path):
    names = parse(open(path, "rb").read())
    strings = [{"id": i, "jp": n, "en": "", "budget": NAME - 1} for i, n in enumerate(names) if n]
    return {"file": os.path.basename(path), "format": "MTI", "strings": strings}


def build(orig_path, ws):
    data = bytearray(open(orig_path, "rb").read())
    names = parse(bytes(data))
    for e in ws["strings"]:
        i = e["id"]
        if names[i] != e["jp"]:
            raise ValueError("record %d: original name mismatch" % i)
        text = e["en"] if e.get("en") else e["jp"]
        b = text.encode("utf-8")
        if len(b) > NAME - 1:
            raise ValueError("record %d: %d bytes > %d: %r" % (i, len(b), NAME - 1, text))
        o = HEADER + i * REC
        data[o:o + NAME] = b + bytes(NAME - len(b))
    return bytes(data)


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "extract":
        ws = extract(argv[2])
        json.dump(ws, open(argv[3], "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
        print("%d strings" % len(ws["strings"]))
    elif cmd == "build":
        out = build(argv[2], json.load(open(argv[3], encoding="utf-8")))
        open(argv[4], "wb").write(out)
        print("wrote", argv[4])
    elif cmd == "roundtrip":
        same = build(argv[2], extract(argv[2])) == open(argv[2], "rb").read()
        print("roundtrip:", "identical" if same else "DIFFERS")
        return 0 if same else 1
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
