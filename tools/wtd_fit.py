#!/usr/bin/env python3
"""Find WTD labels whose English is wider than the room the layout gives them.

Uses wtd.py's element geometry (per occurrence: glyph cell size w, left/
centre/right alignment, and "room" = px from the text's own x to the next
object on the same row) and the proportional font's advances (fitcheck
Font). The on-screen width of the English is sum(advance) * w / 32.

Usage: wtd_fit.py WORKSHEET.json ORIGINAL.wtd [--min-scale 0.7] [--apply]
  --apply   write "font_px" into the worksheet for every overflowing string
            whose text fits at >= min-scale of its current size (the rest
            are listed for shortening by hand)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import fitcheck  # noqa: E402
import wtd  # noqa: E402


def nearest_beyond(geo, o, min_dx):
    """Nearest object base record in the same group/row at least min_dx to
    the right of occurrence o (None if nothing there)."""
    tree = geo["_tree"]
    el = tree[o["element"]]
    g = el["groups"][o["group"]]
    hh = max(o.get("h") or 24.0, 20.0)
    best = None
    for i, ob2 in enumerate(g["objects"]):
        if i == o["object"] or not ob2["parts"] or "x" not in ob2["parts"][0]:
            continue
        b2 = ob2["parts"][0]
        dx = g["x"] + b2["x"] - o["x"]
        if dx >= min_dx and abs(g["y"] + b2.get("y", 0.0) - o["y"]) < hh and (best is None or dx < best):
            best = dx
    return best


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    ws_path, orig = argv[1], argv[2]
    min_scale = float(argv[argv.index("--min-scale") + 1]) if "--min-scale" in argv else 0.7
    apply = "--apply" in argv
    ws = json.load(open(ws_path, encoding="utf-8"))
    geo = wtd.geometry(orig)
    geo["_tree"] = wtd.parse_tree(open(orig, "rb").read())[1]
    by_jp = {e["jp"]: e for e in geo["strings"]}
    font = fitcheck.Font(fitcheck.DEFAULT_FONT)
    rows = []
    for e in ws["strings"]:
        en = e.get("en")
        if not en or e["jp"] not in by_jp:
            continue
        en_w32 = font.width(en.replace("\n", ""))
        worst = None
        for o in by_jp[e["jp"]]["occurrences"]:
            if not o.get("w") or o.get("room") is None:
                continue
            w = o["w"]
            en_px = en_w32 * w / 32.0
            room = o["room"]
            # A neighbour closer than the Japanese text itself is a shadow
            # copy or a value drawn inside the label, not a real limit.
            if o.get("text_w") and room < o["text_w"] - 2:
                room = o["room"] = nearest_beyond(geo, o, o["text_w"] - 2)
                if room is None:
                    continue
            if o.get("align") == "center":
                room = max(room, o["text_w"]) if o.get("text_w") else room
            room -= 4                        # keep a visible gap to the neighbour
            if en_px > room and (worst is None or en_px / room > worst[0]):
                worst = (en_px / room, o, en_px, room)
        if worst:
            ratio, o, en_px, room = worst
            need = o["w"] * room / en_px      # cell size that would fit
            rows.append((ratio, e, o, en_px, room, need))
    rows.sort(key=lambda r: -r[0])
    n_apply = 0
    for ratio, e, o, en_px, room, need in rows:
        fits = need >= o["w"] * min_scale
        mark = "scale %.0f->%.0f" % (o["w"], need) if fits else "SHORTEN"
        print("#%-4s el%-3s %-9s w%-3.0f en %4.0fpx > room %4.0fpx  %-14s %s  <-  %s" % (
            e["id"], o["element"], o.get("align"), o["w"], en_px, room, mark, e["en"].replace("\n", "\\n"), e["jp"]))
        if apply and fits:
            e["font_px"] = int(need)
            n_apply += 1
    print("%d overflowing; %d scaled" % (len(rows), n_apply))
    if apply:
        json.dump(ws, open(ws_path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
