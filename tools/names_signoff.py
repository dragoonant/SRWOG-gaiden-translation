#!/usr/bin/env python3
"""Build glossary/signoff.tsv: every pilot, unit, weapon, spirit and skill
name in the game's data tables, matched against the PS2-patch glossary.

Matching normalises both sides (NFKC, unified dashes and middle dots,
spaces removed). Pilots also match on the first part of a glossary full
name ("マサキ" matches "マサキ・アンドー"). Unmatched rows get an empty
English column for a proposal and sign-off.

Columns: category, jp, en, match, glossary_jp, notes
match: exact | first-name | none

Usage: names_signoff.py   (run from anywhere; paths are repo-relative)
"""
import csv
import json
import os
import sys
import unicodedata

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(REPO, "worksheets", "Logic", "Dat", "FixedData")

TABLES = [
    ("pilot", "PilotData.dat", "name", "pilots.tsv"),
    ("unit", "UnitData.dat", "name", "units.tsv"),
    ("weapon", "WeaponData.dat", "name", "attacks.tsv"),
    ("spirit", "SpiritData.dat", "name", "spirits.tsv"),
    ("skill", "SkillData.dat", "name", "skills.tsv"),
]
DASHES = "‐‑‒–—―－ー-"


def norm(s):
    s = unicodedata.normalize("NFKC", s)
    for d in "‐‑‒–—―－":
        s = s.replace(d, "-")
    s = s.replace("・", "").replace("･", "").replace("=", "").replace("＝", "")
    return "".join(s.split())


def load_glossary(fname):
    rows = {}
    first = {}
    path = os.path.join(REPO, "glossary", fname)
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            jp = (r.get("jp") or "").strip()
            if not jp:
                continue
            rows.setdefault(norm(jp), (jp, r.get("en", "").strip()))
            head = jp.split("・")[0]
            first.setdefault(norm(head), (jp, r.get("en", "").strip()))
    return rows, first


def game_names(fname, label):
    ws = json.load(open(os.path.join(FIX, fname + ".json"), encoding="utf-8"))
    seen = []
    for e in ws["strings"]:
        if e.get("keep"):
            continue
        if any(r.endswith("." + label) for r in e.get("refs", [])):
            t = e.get("text") or "\n".join(e.get("lines", []))
            if t not in seen and t not in ("ダミー",) and not set(t) <= set("－？-?"):
                seen.append(t)
    return seen


def main():
    out_rows = []
    summary = []
    for cat, fname, label, gfile in TABLES:
        exact, first = load_glossary(gfile)
        names = game_names(fname, label)
        hit = 0
        for n in names:
            k = norm(n)
            if k in exact:
                jp, en = exact[k]
                out_rows.append([cat, n, en, "exact", jp, ""])
                hit += 1
            elif cat == "pilot" and k in first:
                jp, en = first[k]
                out_rows.append([cat, n, en.split()[0] if en else "", "first-name", jp, "short name; full: " + en])
                hit += 1
            else:
                out_rows.append([cat, n, "", "none", "", ""])
        summary.append((cat, len(names), hit))
    dst = os.path.join(REPO, "glossary", "signoff.tsv")
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["category", "jp", "en", "match", "glossary_jp", "notes"])
        w.writerows(out_rows)
    for cat, n, hit in summary:
        print("%-7s %4d names, %4d matched (%d%%)" % (cat, n, hit, 100 * hit // max(n, 1)))
    print("wrote", dst)


if __name__ == "__main__":
    main()
