#!/usr/bin/env python3
"""Put English into keyword tags in every worksheet translation.

Story and library text marks glossary keywords as <イスルギ重工>. The game
prints the text inside the tag as written (seen in game: "<プロジェクトＴＤ>"
displayed in Japanese), so the English must go inside. KeyWordData's own
names are translated, which keeps tag text and dictionary names identical.

Modes:
  tag    <イスルギ重工>  ->  <Isurugi Heavy Industries>   (keeps the tag)
  plain  <イスルギ重工>  ->  Isurugi Heavy Industries     (drops the tag)
Only tags whose Japanese (line breaks removed) is a KeyWordData name are
touched; formatting tags (<W=28>, </C>, ...) never are.

Usage: keyword_tags.py tag|plain [--dry-run]
Also updates translations/tm.json so repeats stay consistent.
"""
import glob
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAG = re.compile(r"<([^<>=/]+)>")


def keyword_names():
    kw = json.load(open(os.path.join(REPO, "worksheets", "Logic", "Dat", "FixedData", "KeyWordData.dat.json"),
                        encoding="utf-8"))
    out = {}
    for e in kw["strings"]:
        t = e.get("text")
        if t and e.get("en") and "\n" not in t and "\n" not in e["en"]:
            out[t] = e["en"]
    return out


def main(argv):
    mode = argv[1] if len(argv) > 1 else ""
    if mode not in ("tag", "plain"):
        print(__doc__)
        return 2
    dry = "--dry-run" in argv
    names = keyword_names()

    def fix(m):
        key = m.group(1).replace("\n", "").replace("@", "")
        if key not in names:
            return m.group(0)
        return ("<%s>" % names[key]) if mode == "tag" else names[key]

    tm_path = os.path.join(REPO, "translations", "tm.json")
    tm = json.load(open(tm_path, encoding="utf-8")) if os.path.exists(tm_path) else {}
    changed_entries = changed_files = 0
    for p in glob.glob(os.path.join(REPO, "worksheets", "**", "*.json"), recursive=True):
        ws = json.load(open(p, encoding="utf-8"))
        fmt = str(ws.get("format", "")).split()[0]
        dirty = False
        for e in ws["strings"]:
            en = e.get("en")
            if not en or "<" not in en:
                continue
            new = TAG.sub(fix, en)
            if new != en:
                e["en"] = new
                dirty = True
                changed_entries += 1
                jp = e.get("jp") or e.get("text") or "\n".join(e.get("lines", []))
                if fmt + "\t" + jp in tm:
                    tm[fmt + "\t" + jp] = new
        if dirty:
            changed_files += 1
            if not dry:
                json.dump(ws, open(p, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    if not dry:
        json.dump(tm, open(tm_path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=0)
    print("%s: %d entries in %d worksheets%s" % (mode, changed_entries, changed_files, " (dry run)" if dry else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
