#!/usr/bin/env python3
"""Repaint the stage-title card textures (Common/Dat/SceneTitle) in English.

Two kinds of strip, both uncompressed 32-bit BGRA DDS (128-byte header):

  st_NNN.dds  1120 x 3072 = 12 frames of 1120 x 256, the stage title
              (Japanese glyphs 68 px tall, centred on (560, 128)):
                f1-f8   reveal: white glyphs x a cloud/noise mask (one
                        noise field per frame, shared by every stage;
                        frames 2-8 repeat horizontally every 560 px)
                f9      solid white
                f10-f12 cyan (2,180,196) outer glow, glyph knocked out
                        (tight / wide / faint)
  sn_NNN.dds  256 x 672 = 7 frames of 256 x 96, "第 N 話" (glyphs 55 px
              tall, centred on (127.5, 47.5)):
                f1-f4   reveal (as above)
                f5      solid white, 1 px cyan-tinted anti-alias fringe
                f6      cyan outer glow, knocked out
                f7      white outer glow (thin outline), knocked out

NNN is the stage id (byte 0 of the 16-byte StageData record), not the
record index; the English title is the "en" of the StageData.dat.json
string whose refs include "recK.title" for the record K with that id.
The number card reads "Scenario NNN" ("Final Scenario" for sn_999, 最終話).

The noise masks are recovered from the originals: inside the solid
glyph (alpha 255) a reveal frame's alpha *is* the mask, so the union
over every stage of those pixels gives most of the central band; the
560 px period fills the sides for frames 2-8, small holes are filled by
normalised convolution and anything outside the recovered band is
mirrored in. The result is deterministic.

Usage:
  scene_title.py render ORIG_DIR OUT_DIR STAGEDATA_JSON [--dat STAGEDATA_DAT]
                 [--font FONT.ttf] [--dump-noise DIR]
  scene_title.py preview STRIP.dds OUT.png
"""
import glob
import json
import os
import re
import struct
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageStat

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from texture_text import load_dds, save_dds  # noqa: E402

FONT = r"C:\Windows\Fonts\arialbd.ttf"
WHITE = (255, 255, 255)
CYAN = (2, 180, 196)

# Per-kind layout and the measured animation (sigma/gain of the outer glow
# were fitted against st_001 / sn_001 with Pillow's GaussianBlur).
KINDS = {
    "st": dict(size=(1120, 3072), fh=256, frames=12, reveal=range(1, 9), solid=9,
               cap=68, centre=(560.0, 128.0), max_w=1040, period=560,
               glow={10: (5, 0.66, CYAN), 11: (12, 0.68, CYAN), 12: (4, 0.37, CYAN)},
               fringe=False),
    "sn": dict(size=(256, 672), fh=96, frames=7, reveal=range(1, 5), solid=5,
               cap=55, centre=(127.5, 47.5), max_w=240, period=None,
               glow={6: (8, 0.71, CYAN), 7: (2.5, 0.64, WHITE)},
               fringe=True),
}


# ----------------------------------------------------------------- stage data
def load_titles(json_path, dat_path, orig_dir):
    """Return {stage_id: english title} from the worksheet + the raw records."""
    d = json.load(open(json_path, encoding="utf-8"))
    if not dat_path:
        cands = [json_path[:-5] if json_path.lower().endswith(".json") else "",
                 os.path.join(orig_dir, "..", "..", "..", "Logic", "Dat", "FixedData", "StageData.dat")]
        dat_path = next((c for c in cands if c and os.path.exists(c)), None)
        if not dat_path:
            sys.exit("StageData.dat not found; pass --dat")
    raw = open(dat_path, "rb").read()
    data = next(s for s in d["sections"] if s["magic"] == "DATA")
    rec_size = d["records"]["size"]
    en = {}
    for e in d["strings"]:
        for r in e.get("refs", []):
            m = re.fullmatch(r"rec(\d+)\.title", r)
            if m and e.get("en"):
                en[int(m.group(1))] = e["en"]
    titles = {}
    for i in range(data["count"]):
        sid = raw[data["payload_offset"] + rec_size * i]
        if i in en and sid not in titles:
            titles[sid] = en[i]
    return titles


# --------------------------------------------------------------- originals
def scan(orig_dir):
    """Yield (kind, stage_id, relpath) for every standard-layout strip."""
    out, odd = [], []
    for p in sorted(glob.glob(os.path.join(orig_dir, "**", "s[tn]_[0-9][0-9][0-9].dds"), recursive=True)):
        rel = os.path.relpath(p, orig_dir)
        base = os.path.basename(p)
        kind = base[:2]
        try:
            h, w = struct.unpack_from("<II", open(p, "rb").read(32), 12)
        except struct.error:
            odd.append((rel, "unreadable")); continue
        fourcc = open(p, "rb").read(88)[84:88]
        if fourcc != b"\0\0\0\0":
            odd.append((rel, "compressed %s" % fourcc.decode("ascii", "replace"))); continue
        if (w, h) != KINDS[kind]["size"]:
            odd.append((rel, "unexpected size %dx%d" % (w, h))); continue
        out.append((kind, int(base[3:6]), rel))
    return out, odd


def frame(im, k, fh):
    return im.crop((0, (k - 1) * fh, im.width, k * fh))


# ------------------------------------------------------------ noise masks
def recover_noise(orig_dir, strips, kind):
    """Rebuild each reveal frame's full-frame noise mask for one kind."""
    spec = KINDS[kind]
    w, fh = spec["size"][0], spec["fh"]
    known = Image.new("L", (w, fh), 0)
    noise = {f: Image.new("L", (w, fh), 0) for f in spec["reveal"]}
    for k, sid, rel in strips:
        if k != kind:
            continue
        _, im, _ = load_dds(os.path.join(orig_dir, rel))
        solid = frame(im, spec["solid"], fh).getchannel("A")
        inside = solid.point(lambda v: 255 if v >= 250 else 0)
        new = ImageChops.subtract(inside, known)
        for f in spec["reveal"]:
            noise[f].paste(frame(im, f, fh).getchannel("A"), (0, 0), new)
        known = ImageChops.add(known, new)
    out = {}
    for f in spec["reveal"]:
        out[f] = complete(noise[f], known, spec["period"])
    return out


def complete(noise, known, period):
    """Fill the unknown pixels of a partially known noise field."""
    w, h = noise.size
    if period and w % period == 0:
        # offset wraps around, so a shift by the period folds the copies.
        shifted_k = ImageChops.offset(known, period, 0)
        shifted_n = ImageChops.offset(noise, period, 0)
        both = ImageChops.multiply(known, shifted_k)
        err = ImageStat.Stat(ImageChops.difference(noise, shifted_n), both).mean[0]
        if err < 2.0:                             # the period really holds
            new = ImageChops.subtract(shifted_k, known)
            noise.paste(shifted_n, (0, 0), new)
            known = ImageChops.add(known, new)
    bbox = known.getbbox()
    band_n, band_k = noise.crop(bbox), known.crop(bbox)
    for sigma in (1.5, 3, 6, 12, 24, 48):
        band_n, band_k = nc_fill(band_n, band_k, sigma)
        if band_k.getextrema()[0] == 255:
            break
    return mirror_out(band_n, bbox, (w, h))


def nc_fill(noise, known, sigma, min_den=12):
    """Normalised-convolution fill of unknown pixels near known ones."""
    num = noise.filter(ImageFilter.GaussianBlur(sigma)).tobytes()
    den = known.filter(ImageFilter.GaussianBlur(sigma)).tobytes()
    nb, kb = bytearray(noise.tobytes()), bytearray(known.tobytes())
    for i in range(len(nb)):
        if kb[i] == 0 and den[i] >= min_den:
            nb[i] = min(255, num[i] * 255 // den[i])
            kb[i] = 255
    return (Image.frombytes("L", noise.size, bytes(nb)),
            Image.frombytes("L", known.size, bytes(kb)))


def mirror_out(band, bbox, size):
    """Tile `band` (placed at bbox) over `size` by reflection."""
    x0, y0, x1, y1 = bbox
    bw, bh = x1 - x0, y1 - y0
    out = Image.new("L", size, 0)
    flipped_h = band.transpose(Image.FLIP_LEFT_RIGHT)
    # horizontal strip of reflected copies covering the width
    strip = Image.new("L", (size[0], bh), 0)
    i = -((x0 + bw - 1) // bw) - 1
    while True:
        x = x0 + i * bw
        if x >= size[0]:
            break
        strip.paste(band if i % 2 == 0 else flipped_h, (x, 0))
        i += 1
    flipped_v = strip.transpose(Image.FLIP_TOP_BOTTOM)
    j = -((y0 + bh - 1) // bh) - 1
    while True:
        y = y0 + j * bh
        if y >= size[1]:
            break
        out.paste(strip if j % 2 == 0 else flipped_v, (0, y))
        j += 1
    return out


# ------------------------------------------------------------------ text
def fit_font(text, font_path, cap, max_w):
    """Largest size whose 'H' is <= cap px tall and whose ink fits max_w."""
    size = max(8, cap)
    font = ImageFont.truetype(font_path, size)
    while True:                                    # grow to the cap height
        nxt = ImageFont.truetype(font_path, size + 1)
        l, t, r, b = nxt.getbbox("H")
        if b - t > cap:
            break
        size, font = size + 1, nxt
    while size > 8:                                # shrink to the width
        l, t, r, b = font.getbbox(text)
        if r - l <= max_w:
            break
        size -= 1
        font = ImageFont.truetype(font_path, size)
    return font


def text_mask(text, font, size, centre, cap):
    """L image of `text`, caps centred on `centre` (cap height band)."""
    w, h = size
    l, t, r, b = font.getbbox("H")
    cap_h = b - t
    cx, cy = centre
    baseline = cy + cap_h / 2.0
    l, t, r, b = font.getbbox(text, anchor="ls")
    x = cx - (l + r) / 2.0
    layer = Image.new("L", (w, h), 0)
    ImageDraw.Draw(layer).text((x, baseline), text, font=font, fill=255, anchor="ls")
    return layer


# --------------------------------------------------------------- frames
def outer_glow(mask, sigma, gain):
    blur = mask.filter(ImageFilter.GaussianBlur(sigma))
    glow = blur.point(lambda v: min(255, int(v * gain + 0.5)))
    knock = mask.point(lambda v: 0 if v >= 250 else 255)
    return ImageChops.multiply(glow, knock)


def build_strip(kind, text, noise, font_path):
    spec = KINDS[kind]
    w, fh = spec["size"][0], spec["fh"]
    font = fit_font(text, font_path, spec["cap"], spec["max_w"])
    full = fit_font("H", font_path, spec["cap"], 10 ** 6).size
    mask = text_mask(text, font, (w, fh), spec["centre"], spec["cap"])
    strip = Image.new("RGBA", spec["size"], WHITE + (0,))
    for f in range(1, spec["frames"] + 1):
        if f in noise:
            fr = Image.new("RGBA", (w, fh), WHITE + (0,))
            fr.putalpha(ImageChops.multiply(mask, noise[f]))
        elif f == spec["solid"]:
            if spec["fringe"]:
                # colour = lerp(cyan, white, alpha): the original's AA fringe
                a = mask
                ch = [a.point(lambda v, c=c: c + (255 - c) * v // 255) for c in CYAN]
                fr = Image.merge("RGBA", ch + [a])
            else:
                fr = Image.new("RGBA", (w, fh), WHITE + (0,))
                fr.putalpha(mask)
        elif f in spec["glow"]:
            sigma, gain, colour = spec["glow"][f]
            fr = Image.new("RGBA", (w, fh), colour + (0,))
            fr.putalpha(outer_glow(mask, sigma, gain))
        else:
            raise ValueError("frame %d of %s has no recipe" % (f, kind))
        strip.paste(fr, (0, (f - 1) * fh))
    return strip, font.size, full


# ----------------------------------------------------------------- commands
def render(orig_dir, out_dir, json_path, dat_path=None, font_path=FONT, dump=None):
    titles = load_titles(json_path, dat_path, orig_dir)
    strips, odd = scan(orig_dir)
    noise = {k: recover_noise(orig_dir, strips, k) for k in KINDS}
    if dump:
        os.makedirs(dump, exist_ok=True)
        for k in noise:
            for f, im in noise[k].items():
                im.save(os.path.join(dump, "%s_noise_f%d.png" % (k, f)))
    done, skipped = [], [(rel, why) for rel, why in odd]
    for kind, sid, rel in strips:
        if kind == "st":
            text = titles.get(sid)
            if not text:
                skipped.append((rel, "stage %d has no English title" % sid)); continue
        else:
            # sn_999 is the "最終話" (final episode) card, not a number
            text = "Final Scenario" if sid == 999 else "Scenario %d" % sid
        hdr, im, tail = load_dds(os.path.join(orig_dir, rel))
        strip, size, full = build_strip(kind, text, noise[kind], font_path)
        dst = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        save_dds(dst, hdr, strip, tail)
        done.append((rel, text, size, full))
    print("rendered %d strips (%d st, %d sn)" % (
        len(done), sum(1 for d in done if "st_" in d[0]), sum(1 for d in done if "sn_" in d[0])))
    small = [(r, t, s, f) for r, t, s, f in done if "st_" in r and s < f]
    if small:
        print("st titles reduced below full size (%d):" % len(small))
        for r, t, s, f in small:
            print("  %s  size %d/%d  %s" % (os.path.basename(r), s, f, t))
    sn = [(s, f) for r, t, s, f in done if "sn_" in r]
    if sn:
        print("sn 'Scenario N' size %d-%d (full %d)" % (min(x[0] for x in sn), max(x[0] for x in sn), sn[0][1]))
    if skipped:
        print("skipped %d:" % len(skipped))
        for r, why in skipped:
            print("  %s: %s" % (r, why))
    return done, skipped


def preview(dds_path, out_png, bg=(40, 40, 60)):
    """Frames of a strip laid out in a grid over a dark background."""
    _, im, _ = load_dds(dds_path)
    kind = os.path.basename(dds_path)[:2]
    fh = KINDS.get(kind, {}).get("fh") or (im.height // 7 if im.width == 256 else 256)
    n = im.height // fh
    cols = max(1, min(n, 4480 // im.width))
    rows = (n + cols - 1) // cols
    gap = 4
    sheet = Image.new("RGB", (cols * (im.width + gap) - gap, rows * (fh + gap) - gap), (255, 0, 255))
    back = Image.new("RGBA", (im.width, fh), bg + (255,))
    for i in range(n):
        fr = Image.alpha_composite(back, frame(im, i + 1, fh))
        ImageDraw.Draw(fr).text((4, 2), "f%d" % (i + 1), fill=(255, 200, 0, 255))
        sheet.paste(fr.convert("RGB"), ((i % cols) * (im.width + gap), (i // cols) * (fh + gap)))
    os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
    sheet.save(out_png)


def main(argv):
    if len(argv) >= 4 and argv[0] == "render":
        kw = {}
        rest = argv[4:]
        while rest:
            flag, val, rest = rest[0], rest[1], rest[2:]
            kw[{"--dat": "dat_path", "--font": "font_path", "--dump-noise": "dump"}[flag]] = val
        render(argv[1], argv[2], argv[3], **kw)
    elif len(argv) == 3 and argv[0] == "preview":
        preview(argv[1], argv[2])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
