#!/usr/bin/env python3
"""Tag every worksheet entry with "kind" and "keep".

kind:
  key    "[...]-..." engine keys (speaker labels, event keys). The engine
         matches these byte for byte; translating them skips interludes and
         silences stage music, so they stay Japanese.
  ascii  ASCII-only strings: asset paths, file names, ids, empty strings.
  name   short label without sentence punctuation (speaker names, unit
         names, menu items). Translated through the glossary.
  text   everything else (dialogue, descriptions).
  comment / internal / orphan
         FIXH roles from fixh.py: developer comments the game never shows,
         engine ids (trophy ids, image names), unreferenced strings.
keep: true for key, ascii, comment, internal, orphan. The translation pass must leave "en" empty
for kept entries, and the fit check rejects any that are filled.

Usage: classify.py [WORKSHEET_DIR]   (default: worksheets/ next to tools/)
Prints counts per format and kind. Rewrites files only when tags change.
"""
import collections
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

KEY = re.compile(r"^\[[^\]]*\]-")
ASCII = re.compile(r"[\x00-\x7e]*")
KEEP = ("key", "ascii", "comment", "internal", "orphan")
SENTENCE = re.compile(r"[。、！？「」（）『』…@\n]")


def entry_text(e):
    if "jp" in e:
        return e["jp"]
    if "text" in e:
        return e["text"]
    return "\n".join(e.get("lines", []))


def kind_of(s):
    if KEY.match(s):
        return "key"
    if ASCII.fullmatch(s):
        return "ascii"
    if len(s) <= 16 and not SENTENCE.search(s):
        return "name"
    return "text"


def main(argv):
    root = argv[1] if len(argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "worksheets")
    counts = collections.Counter()
    changed = 0
    for dirpath, _, files in os.walk(root):
        for f in files:
            if not f.endswith(".json"):
                continue
            p = os.path.join(dirpath, f)
            ws = json.load(open(p, encoding="utf-8"))
            dirty = False
            for e in ws.get("strings", []):
                k = kind_of(entry_text(e))
                if e.get("role") in ("comment", "internal", "orphan"):
                    k = e["role"]          # FIXH: never shown, or engine ids
                keep = k in KEEP
                if e.get("kind") != k or e.get("keep") != keep:
                    e["kind"], e["keep"] = k, keep
                    dirty = True
                counts[(ws.get("format"), k)] += 1
            if dirty:
                with open(p, "w", encoding="utf-8", newline="\n") as out:
                    json.dump(ws, out, ensure_ascii=False, indent=1)
                changed += 1
    for (fmt, k), n in sorted(counts.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
        print("%-22s %-6s %7d" % (fmt, k, n))
    total = sum(counts.values())
    keep = sum(n for (fmt, k), n in counts.items() if k in KEEP)
    print("total %d entries, %d kept as-is, %d to translate; %d files updated" % (total, keep, total - keep, changed))


if __name__ == "__main__":
    main(sys.argv)
