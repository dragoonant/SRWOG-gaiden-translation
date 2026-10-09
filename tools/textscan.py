#!/usr/bin/env python3
"""Survey files for Japanese text in Shift-JIS, UTF-8 and UTF-16 (BE/LE).

Counts runs of >= MIN_CHARS consecutive Japanese characters per encoding
and prints one line per file with a non-zero count, plus a sample.

Usage: textscan.py DIR_OR_FILE [--min N] [--top N] [--ext .bin]
"""
import os
import re
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MIN_CHARS = 4
# A genuine Japanese string nearly always has two kana in a row.
KANA = re.compile(r"[぀-ヿ]{2}")

# Shift-JIS double-byte: lead 0x81-0x9F / 0xE0-0xFC, trail 0x40-0x7E / 0x80-0xFC
SJIS = re.compile(rb"(?:[\x81-\x9f\xe0-\xfc][\x40-\x7e\x80-\xfc]){%d,}" % MIN_CHARS)
# UTF-8 three-byte CJK / kana / fullwidth
UTF8 = re.compile(rb"(?:\xe3[\x80-\x83][\x80-\xbf]|[\xe4-\xe9][\x80-\xbf][\x80-\xbf]|\xef[\xbc-\xbf][\x80-\xbf]){%d,}" % MIN_CHARS)
# UTF-16BE: kana 0x3040-0x30FF, CJK 0x4E00-0x9FFF, fullwidth 0xFF00-0xFF5F
U16BE = re.compile(rb"(?:\x30[\x40-\xff]|[\x4e-\x9f][\x00-\xff]|\xff[\x00-\x5f]){%d,}" % MIN_CHARS)
U16LE = re.compile(rb"(?:[\x40-\xff]\x30|[\x00-\xff][\x4e-\x9f]|[\x00-\x5f]\xff){%d,}" % MIN_CHARS)


def scan_bytes(data):
    res = {}
    for name, rx, dec in (("sjis", SJIS, "shift_jis"), ("utf8", UTF8, "utf-8"),
                          ("u16be", U16BE, "utf-16-be"), ("u16le", U16LE, "utf-16-le")):
        runs = rx.findall(data)
        if name == "sjis":
            # sjis matches are 2-byte pairs; be conservative: require the run to decode
            good = []
            for r in runs:
                try:
                    s = r.decode("shift_jis")
                    if KANA.search(s):
                        good.append(s)
                except UnicodeDecodeError:
                    pass
            runs = good
        else:
            good = []
            for r in runs:
                try:
                    s = r.decode(dec)
                    if KANA.search(s):
                        good.append(s)
                except UnicodeDecodeError:
                    pass
            runs = good
        if runs:
            res[name] = (len(runs), sum(len(r) for r in runs), max(runs, key=len)[:40])
    return res


def main(argv):
    target = argv[1]
    top = 60
    ext = None
    if "--top" in argv:
        top = int(argv[argv.index("--top") + 1])
    if "--ext" in argv:
        ext = argv[argv.index("--ext") + 1]
    files = []
    if os.path.isdir(target):
        for root, _, fs in os.walk(target):
            for f in fs:
                if ext is None or f.endswith(ext):
                    files.append(os.path.join(root, f))
    else:
        files = [target]
    rows = []
    for p in files:
        with open(p, "rb") as f:
            data = f.read()
        r = scan_bytes(data)
        if r:
            best = max(r.items(), key=lambda kv: kv[1][1])
            rows.append((best[1][1], p, r))
    rows.sort(reverse=True)
    for total, p, r in rows[:top]:
        rel = os.path.relpath(p, target) if os.path.isdir(target) else p
        parts = ["%s:%d runs/%d chars" % (k, v[0], v[1]) for k, v in r.items()]
        best = max(r.items(), key=lambda kv: kv[1][1])
        print("%-60s %s  e.g. %s" % (rel, "  ".join(parts), best[1][2]))
    print("%d files with Japanese text out of %d scanned" % (len(rows), len(files)))


if __name__ == "__main__":
    main(sys.argv)
