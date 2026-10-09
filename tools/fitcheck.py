#!/usr/bin/env python3
"""Check every translated worksheet entry before a build.

Errors (build must not ship):
  keep      an entry marked keep has an "en"
  tag       the multiset of <...> tags differs from the Japanese
  printf    the sequence of %d/%s/... specifiers differs
  bracket   a stray ASCII < or > outside a tag (the engine eats it)
  lines     more lines than the budget (see below)
  width     a line wider than the budget in pixels
  glossary  a name's Japanese appears in "jp" (outside <keyword> tags) and
            "en" uses a known wrong variant (Akurasu or an earlier proposal
            where canon differs). A canonical term simply not mentioned
            (pronoun, paraphrase) is only counted as a warning.
Warnings: none of the above but en contains Japanese characters.

Line separators: LDBI/LOGO/ELF "@", BMD "/" + U+3000, FIXH newline.
Budgets:
  dialogue (LDBI, BMD): lines <= 3; width <= the 99.5th percentile of the
      Japanese line widths in that format (one shared budget per format).
  everything else: lines <= the Japanese line count of that entry (at least
      1); width <= the widest Japanese line of that entry.
Widths use the game font's advance table with the proportional ASCII
advances that the build generates (tools/fttf.py make_proportional).

Usage: fitcheck.py [--font PATH] [--only FORMAT] [--max N] [--no-glossary] [--json OUT]
  --json writes every error as {path, id, kind, msg} (used by translate_batch.py retry).
  bytes: an EBOOT string longer than its in-place byte budget.
Exit status 1 when there are errors.
"""
import collections
import csv
import glob
import json
import os
import re
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_FONT = r"C:\Users\antho\srw2og-work\ext\Common\Dat\Font\font.bin"
TAG = re.compile(r"<[^<>]*>")
PRINTF = re.compile(r"%[-+#0]?\d*(?:\.\d+)?[hl]?[diouxXfcs]")
JPCHAR = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
DIALOGUE = {"LDBI", "BMD"}
LABEL_PX = 160   # Japanese width of a 5-character label


class Font:
    def __init__(self, path):
        self.d = open(path, "rb").read()
        if self.d[:4] != b"FTTF":
            raise ValueError("not an FTTF font")
        self.cache = {}
        # The build ships proportional ASCII (tools/fttf.py); measure with
        # those advances, not the original uniform 22 px.
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import fttf
        self.cache.update(fttf.make_proportional(fttf.Font(path), write=False))

    def advance(self, ch):
        cp = ord(ch)
        if cp in self.cache:
            return self.cache[cp]
        adv = 32
        if cp <= 0xFFFF:
            blk = struct.unpack_from(">I", self.d, 0x54 + 4 * (cp >> 8))[0]
            if blk:
                a, g = struct.unpack_from(">HH", self.d, blk + 4 * (cp & 0xFF))
                if a or g:
                    adv = a
        self.cache[cp] = adv
        return adv

    def width(self, s):
        return sum(self.advance(c) for c in TAG.sub("", s))


def fmt_of(ws):
    return str(ws.get("format", "")).split()[0]


def jp_of(e):
    if "jp" in e:
        return e["jp"]
    if "text" in e:
        return e["text"]
    return "\n".join(e.get("lines", []))


def split_lines(fmt, s):
    if fmt == "BMD":
        return re.split(r"/\u3000?", s)
    if fmt == "FIXH":
        return s.split("\n")
    return s.split("@")


def load_variants():
    """Known non-canonical spellings per Japanese name: the Akurasu form and
    any earlier proposal recorded in signoff.tsv notes ("was '...'")."""
    out = {}
    p = os.path.join(REPO, "glossary", "signoff.tsv")
    if not os.path.exists(p):
        return out
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="	"):
            en = r.get("en", "")
            alts = {r.get("akurasu", "")} | set(re.findall(r"was '([^']*)'", r.get("notes", "")))
            alts = {a for a in alts if a and a != en and a.lower() not in en.lower()}
            if alts and len(r["jp"]) >= 2:
                out.setdefault(r["jp"], set()).update(alts)
    return out


VARIANTS = load_variants()


def load_glossary():
    """Canon: glossary/signoff.tsv "en" (OGs basis, Anthony's picks) for every
    data-table name; the older glossary TSVs only for terms signoff lacks
    (factions, terrain, ...). Reference tables are not canon."""
    REFERENCE = ("signoff.tsv", "akurasu_og2nd.tsv")
    canon = {}
    p = os.path.join(REPO, "glossary", "signoff.tsv")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                if r.get("en") and len(r["jp"]) >= 2:
                    canon[r["jp"]] = r["en"]
    for p in glob.glob(os.path.join(REPO, "glossary", "*.tsv")):
        if os.path.basename(p) in REFERENCE:
            continue
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                jp, en = (r.get("jp") or "").strip(), (r.get("en") or "").strip()
                if len(jp) >= 2 and en:
                    canon.setdefault(jp, en)
    # A katakana name only counts when no other katakana touches it, so ライ
    # (Rai) does not fire inside サテライト.
    kata = "゠-ヿ"
    out = []
    for jp, en in sorted(canon.items(), key=lambda t: -len(t[0])):
        rx = re.compile("(?<![%s])%s(?![%s])" % (kata, re.escape(jp), kata))
        out.append((jp, en, rx))
    return out


def main(argv):
    font_path = argv[argv.index("--font") + 1] if "--font" in argv else DEFAULT_FONT
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    show = int(argv[argv.index("--max") + 1]) if "--max" in argv else 40
    use_glossary = "--no-glossary" not in argv
    font = Font(font_path)
    sheets = []
    for p in glob.glob(os.path.join(REPO, "worksheets", "**", "*.json"), recursive=True):
        ws = json.load(open(p, encoding="utf-8"))
        if only and fmt_of(ws) != only:
            continue
        sheets.append((os.path.relpath(p, REPO), ws))
    # Shared dialogue width budgets from the Japanese corpus.
    budget = {}
    for fmt in DIALOGUE:
        widths = sorted(font.width(l) for _, ws in sheets if fmt_of(ws) == fmt
                        for e in ws["strings"] if not e.get("keep")
                        for l in split_lines(fmt, jp_of(e)))
        if widths:
            budget[fmt] = widths[min(len(widths) - 1, int(len(widths) * 0.995))]
    glossary = load_glossary() if use_glossary else []
    errors = collections.Counter()
    warnings = 0
    missing = 0
    translated = 0
    shown = 0

    failures = []
    labels = []

    def report(kind, path, e, msg):
        nonlocal shown
        errors[kind] += 1
        failures.append({"path": path, "id": e.get("id"), "kind": kind, "msg": msg})
        if shown < show:
            print("%-8s %s #%s: %s" % (kind, path, e.get("id"), msg))
            shown += 1

    for path, ws in sheets:
        fmt = fmt_of(ws)
        for e in ws["strings"]:
            en = e.get("en") or ""
            if not en:
                continue
            translated += 1
            jp = jp_of(e)
            if e.get("keep"):
                report("keep", path, e, "kept entry has a translation")
                continue
            if fmt == "ELF" and len(en.encode("utf-8")) > e.get("budget", 1 << 30):
                report("bytes", path, e, "%d bytes > %d (replaced in place)" % (len(en.encode("utf-8")), e["budget"]))
            if collections.Counter(TAG.findall(jp)) != collections.Counter(TAG.findall(en)):
                report("tag", path, e, "tags %s vs %s" % (TAG.findall(jp), TAG.findall(en)))
            if PRINTF.findall(jp) != PRINTF.findall(en):
                report("printf", path, e, "%s vs %s" % (PRINTF.findall(jp), PRINTF.findall(en)))
            if re.search(r"[<>]", TAG.sub("", en)):
                report("bracket", path, e, "stray < or > in %r" % en[:60])
            jl, el = split_lines(fmt, jp), split_lines(fmt, en)
            if fmt in DIALOGUE:
                max_lines, max_w = 3, budget.get(fmt, 99999)
            else:
                max_lines, max_w = max(1, len(jl)), max(font.width(l) for l in jl)
            if len(el) > max_lines:
                report("lines", path, e, "%d lines > %d" % (len(el), max_lines))
            for l in el:
                w = font.width(l)
                if w > max_w:
                    if fmt not in DIALOGUE and max_w <= LABEL_PX:
                        # Short label (<= 5 Japanese characters): the real box is
                        # usually wider than the Japanese text. Listed for the
                        # in-game check instead of being re-translated shorter.
                        labels.append({"path": path, "id": e.get("id"), "en": en, "px": w, "jp_px": max_w})
                    else:
                        report("width", path, e, "%dpx > %dpx: %r" % (w, max_w, l[:50]))
                    break
            # Glossary. Terms inside <keyword> tags are displayed from the
            # keyword dictionary, so only the untagged text counts. A known
            # wrong variant (e.g. Akurasu's spelling where canon differs) is
            # an error; a term simply not mentioned (pronoun, paraphrase) is
            # only counted.
            jp_plain, en_plain = TAG.sub("", jp), TAG.sub("", en)
            for gjp, gen, rx in glossary:
                if gjp in jp_plain and rx.search(jp_plain):
                    bad = [v for v in VARIANTS.get(gjp, ()) if re.search(r"\b%s\b" % re.escape(v), en_plain)]
                    if bad:
                        report("glossary", path, e, "%s is %r here; canon is %r" % (gjp, bad[0], gen))
                    elif gen.lower() not in en_plain.lower():
                        missing += 1
            if JPCHAR.search(TAG.sub("", en)):
                warnings += 1
    print("checked %d translated entries in %d worksheets" % (translated, len(sheets)))
    print("dialogue width budgets: %s" % ", ".join("%s %dpx" % kv for kv in sorted(budget.items())))
    print("errors: %s; warnings: %d Japanese outside tags, %d glossary terms not mentioned"
          % (dict(errors) or "none", warnings, missing))
    if labels:
        json.dump(labels, open(os.path.join(REPO, "translations", "label_widths.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("%d short labels wider than their Japanese: listed in translations/label_widths.json "
              "for the in-game check" % len(labels))
    if "--json" in argv:
        json.dump(failures, open(argv[argv.index("--json") + 1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
