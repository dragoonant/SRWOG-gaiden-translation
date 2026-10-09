#!/usr/bin/env python3
"""Compare the name sheet against the English of the OGs (PS2) fan patch.

The OGs patch is the translation basis; Akurasu (glossary/akurasu_og2nd.tsv)
is the reference it should agree with. For every row of
glossary/signoff.tsv this finds:
  ogs       the form used in the OGs patch text (most frequent candidate)
  akurasu   the Akurasu OG2nd form, when Akurasu has a JP/EN pair
and sets en = ogs when the OGs patch has the name, else akurasu, else the
existing proposal. Rows where both exist and differ go to deviations.md.

OGs text comes from xdelta_added.py output: the partial image plus its
known-range map. Accented letters in that patch are single bytes
(0xA2 = ä, 0xB9 = ü, 0xA6 = è).

Usage: ogs_compare.py OGS_IMAGE OGS_MAP.json
"""
import collections
import csv
import json
import mmap
import os
import re
import sys
import unicodedata

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIGH = {0xA2: "ä", 0xB9: "ü", 0xA6: "è"}
PHRASE = re.compile(r"[A-Z][\w'’.\-]*(?:[ \-][A-Z0-9][\w'’.\-]*){0,5}")


def ogs_text(image, mapfile):
    m = json.load(open(mapfile))
    f = open(image, "rb")
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    trans = bytes(range(256))
    parts = []
    allowed = re.compile(rb"[\x20-\x7e\x0a\xa2\xb9\xa6]{4,}")
    for a, b in m["known_ranges"]:
        if b - a < 4:
            continue
        for s in allowed.findall(mm[a:b]):
            t = "".join(HIGH.get(c, chr(c)) for c in s)
            if sum(ch.isalpha() for ch in t) >= 3:
                parts.append(t)
    return "\n".join(parts)


def fold(s):
    """Loose key: no accents, long vowels collapsed, no spaces/punctuation."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]", "", s)
    s = s.replace("ou", "o").replace("uu", "u").replace("oo", "o").replace("ee", "e").replace("aa", "a")
    return s


def main(argv):
    text = ogs_text(argv[1], argv[2])
    phrases = collections.Counter(m.group().strip(" .-") for m in PHRASE.finditer(text))
    folded = collections.defaultdict(collections.Counter)
    for p, n in phrases.items():
        folded[fold(p)][p] += n
    words = collections.Counter(re.findall(r"[A-Za-zäüè][\w'’\-]*", text))

    def ogs_count(form):
        if not form:
            return 0
        if " " not in form and "-" not in form:
            return words.get(form, 0)
        return len(re.findall(r"(?<![\w])%s(?![\w])" % re.escape(form), text))

    ak = {}
    for r in csv.DictReader(open(os.path.join(REPO, "glossary", "akurasu_og2nd.tsv"), encoding="utf-8"), delimiter="\t"):
        ak.setdefault((r["page"], r["jp"]), r["en"])
    p = os.path.join(REPO, "glossary", "signoff.tsv")
    rows = list(csv.DictReader(open(p, encoding="utf-8"), delimiter="\t"))
    hdr = list(rows[0].keys())
    for col in ("ogs", "ogs_count", "akurasu"):
        if col not in hdr:
            hdr.insert(hdr.index("notes"), col)
    stats = collections.Counter()
    devs = collections.defaultdict(list)
    for r in rows:
        akform = r["en"] if r["match"] == "akurasu" else ""
        was = re.findall(r"was '([^']*)'", r["notes"]) + re.findall(r'was "([^"]*)"', r["notes"])
        cands = [c for c in [r["en"]] + was if c]
        best, best_n = "", 0
        for c in cands:
            n = ogs_count(c)
            if n > best_n:
                best, best_n = c, n
        if not best_n:                     # loose match on spelling variants
            for c in cands:
                for form, n in folded.get(fold(c), {}).items():
                    if n > best_n and len(form) >= 3:
                        best, best_n = form, n
        if best_n < 2:
            best, best_n = "", 0
        r["ogs"], r["ogs_count"], r["akurasu"] = best, str(best_n or ""), akform
        if best:
            if akform and akform != best:
                devs[r["category"]].append((r["jp"], best, best_n, akform))
                stats["deviation"] += 1
            elif akform:
                stats["agree"] += 1
            else:
                stats["ogs only"] += 1
            r["en"] = best
        else:
            stats["not in OGs"] += 1
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=hdr, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    json.dump({k: v for k, v in devs.items()}, open(os.path.join(REPO, "glossary", "ogs_deviations.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(dict(stats))
    for cat, items in devs.items():
        print(cat, len(items))


if __name__ == "__main__":
    main(sys.argv)
