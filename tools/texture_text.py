#!/usr/bin/env python3
"""Repaint text that is baked into a texture (uncompressed 32-bit DDS).

A spec file (textures/<name>.json) lists the label boxes found in the
original texture and the English for each:

  {"fill": [188,254,255], "glow": [30,47,255], "font": "bahnschrift.ttf",
   "labels": [{"box": [x0,y0,x1,y1], "jp": "援護攻撃", "en": "Support Attack"}]}

Each box (inclusive pixel coordinates, the ink bounds of the Japanese) is
cleared with a 2 px margin and the English is drawn in the same style: a
solid fill over a blurred glow. The English is sized to the box height and
squeezed horizontally to the box width when needed (down to 55%), then
centred in the box, so it occupies the same sprite area the game draws.

Usage: texture_text.py SPEC ORIGINAL.dds OUT.dds [--preview OUT.png]
"""
import json
import os
import struct
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = r"C:\Windows\Fonts"


def load_dds(path):
    d = open(path, "rb").read()
    h, w = struct.unpack_from("<II", d, 12)
    pf_flags, fourcc, bpp = struct.unpack_from("<I4sI", d, 80)
    if fourcc != b"\0\0\0\0" or bpp != 32:
        raise ValueError("%s: only uncompressed 32-bit DDS supported" % path)
    im = Image.frombuffer("RGBA", (w, h), d[128:128 + w * h * 4], "raw", "BGRA", 0, 1).copy()
    return d[:128], im, d[128 + w * h * 4:]


def save_dds(path, header, im, tail):
    raw = im.tobytes("raw", "BGRA")
    open(path, "wb").write(header + raw + tail)


def render_label(text, box_w, box_h, font_path, fill, glow):
    """Return an RGBA image box_w x box_h with the styled text centred."""
    size = box_h
    font = ImageFont.truetype(font_path, size)
    # grow/shrink until the cap height matches the box height
    for _ in range(40):
        l, t, r, b = font.getbbox("HAMgy")
        if b - t <= box_h - 3 or size < 8:
            break
        size -= 1
        font = ImageFont.truetype(font_path, size)
    # Shrink the font until a squeeze of at most 35% fits the box width.
    while True:
        l, t, r, b = font.getbbox(text)
        tw, th = r - l + 6, b - t + 6
        if tw * 0.65 <= box_w or size <= 8:
            break
        size -= 1
        font = ImageFont.truetype(font_path, size)
    layer = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(layer).text((3 - l, 3 - t), text, font=font, fill=255)
    if tw > box_w:                                   # squeeze to the box width
        layer = layer.resize((box_w, th), Image.LANCZOS)
        tw = box_w
    glow_mask = layer.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1.6))
    out = Image.new("RGBA", (box_w, box_h), (glow[0], glow[1], glow[2], 0))
    ox, oy = (box_w - tw) // 2, (box_h - th) // 2
    g = Image.new("RGBA", (tw, th), tuple(glow) + (0,))
    g.putalpha(glow_mask.point(lambda a: int(a * 0.85)))
    f = Image.new("RGBA", (tw, th), tuple(fill) + (0,))
    f.putalpha(layer)
    tile = Image.alpha_composite(g, f)
    out.alpha_composite(tile, (max(0, ox), max(0, oy)))
    return out


def apply(spec_path, src, dst, preview=None):
    spec = json.load(open(spec_path, encoding="utf-8"))
    header, im, tail = load_dds(src)
    font_path = os.path.join(FONT_DIR, spec.get("font", "bahnschrift.ttf"))
    fill, glow = spec["fill"], spec["glow"]
    for lab in spec["labels"]:
        x0, y0, x1, y1 = lab["box"]
        m = 2
        cx0, cy0, cx1, cy1 = max(0, x0 - m), max(0, y0 - m), min(im.width, x1 + 1 + m), min(im.height, y1 + 1 + m)
        im.paste((glow[0], glow[1], glow[2], 0), (cx0, cy0, cx1, cy1))
        tile = render_label(lab["en"], cx1 - cx0, cy1 - cy0, font_path, fill, glow)
        im.alpha_composite(tile, (cx0, cy0))
    save_dds(dst, header, im, tail)
    if preview:
        bg = Image.new("RGBA", im.size, (40, 40, 40, 255))
        bg.alpha_composite(im)
        bg.convert("RGB").save(preview)
    return len(spec["labels"])


def main(argv):
    if len(argv) < 4:
        print(__doc__)
        return 2
    prev = argv[argv.index("--preview") + 1] if "--preview" in argv else None
    n = apply(argv[1], argv[2], argv[3], prev)
    print("repainted %d label(s) -> %s" % (n, argv[3]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
