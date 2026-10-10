#!/usr/bin/env python3
"""Repaint sprite labels baked into an FTTF font's uncompressed ARGB8 texture.

Common/Dat/Font/exFont01.bin only maps ASCII and full-width digits as
glyphs (texture rows 0-351). The rest of its 256 x 2048 texture is a sprite
sheet the game references by fixed UV rectangles: the red italic 援護攻撃 /
blue 援護防御 map overlays, the 攻/反 badges, 再攻撃, 不参加, 合体, 例 and
so on. Each label is repainted inside its own ink bounds so the UV
rectangles still frame it.

Spec (textures/exfont01.json):
  {"texture": "Common/Dat/Font/exFont01.bin", "tool": "exfont_text.py",
   "font": "bahnschrift.ttf",
   "labels": [{"box": [x0,y0,x1,y1], "jp": "援護攻撃", "en": "SUP ATK",
               "fill": [255,50,50], "outline": [0,0,0],
               "italic": true,            # shear the letters like the original
               "inner": true,             # badge: keep the frame, repaint the
                                          #   interior row by row from its
                                          #   left edge before drawing
               "cross": [251,83,0],       # draw an X behind the text
               "variation": "Condensed"}]}
Boxes are exclusive pixel bounds [x0, y0, x1, y1).

Also accepts an uncompressed 32-bit DDS sprite sheet (e.g. the intermission
title in General2d/.../Texture/tex_06.dds).

Usage: exfont_text.py SPEC ORIGINAL.bin|.dds OUT [--preview OUT.png]
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = r"C:\Windows\Fonts"


def load_font_texture(path):
    d = open(path, "rb").read()
    if d[:4] != b"FTTF":
        raise ValueError("%s: not an FTTF font" % path)
    t = struct.unpack_from(">I", d, 0x14)[0]
    data_rel = struct.unpack_from(">I", d, t + 0x10)[0]
    fmt = d[t + 0x18]
    w, h = struct.unpack_from(">HH", d, t + 0x20)
    if fmt & 0x9F != 0x85:
        raise ValueError("%s: texture format 0x%02x is not ARGB8" % (path, fmt))
    off = t + data_rel
    im = Image.frombuffer("RGBA", (w, h), d[off:off + w * h * 4], "raw", "ARGB", 0, 1).copy()
    return d, off, im


def make_font(path, size, variation=None):
    f = ImageFont.truetype(path, size)
    if variation:
        try:
            f.set_variation_by_name(variation)
        except Exception:
            pass
    return f


def render_label(text, box_w, box_h, font_path, fill, outline, italic=False, variation=None, pad=2):
    """RGBA box_w x box_h: text with a 1 px outline, sized to the box
    height, squeezed to the width if needed, centred."""
    size = max(8, box_h)
    while size > 8:
        font = make_font(font_path, size, variation)
        l, t, r, b = font.getbbox(text)
        if b - t + 2 * pad <= box_h:
            break
        size -= 1
    font = make_font(font_path, size, variation)
    l, t, r, b = font.getbbox(text)
    tw, th = r - l + 2 * pad + (4 if italic else 0), b - t + 2 * pad
    layer = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(layer).text((pad - l + (2 if italic else 0), pad - t), text, font=font, fill=255)
    if italic:
        layer = layer.transform(layer.size, Image.AFFINE, (1, 0.22, -0.11 * th, 0, 1, 0), Image.BICUBIC)
    if tw > box_w:
        layer = layer.resize((box_w, th), Image.LANCZOS)
        tw = box_w
    edge = layer.filter(ImageFilter.MaxFilter(3))
    o = Image.new("RGBA", (tw, th), tuple(outline) + (0,))
    o.putalpha(edge)
    f = Image.new("RGBA", (tw, th), tuple(fill) + (0,))
    f.putalpha(layer)
    tile = Image.alpha_composite(o, f)
    out = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    out.alpha_composite(tile, ((box_w - tw) // 2, (box_h - th) // 2))
    return out


def clear_box(im, box, lab):
    x0, y0, x1, y1 = box
    if lab.get("inner"):
        # Badge interior: continue each row's leftmost colour across the row
        # (these badges shade vertically), keeping the frame outside the box.
        px = im.load()
        for y in range(y0, y1):
            c = px[x0, y]
            for x in range(x0, x1):
                px[x, y] = c
    else:
        im.paste((0, 0, 0, 0), (x0, y0, x1, y1))
    if lab.get("cross"):
        d = ImageDraw.Draw(im)
        col = tuple(lab["cross"]) + (255,)
        d.line((x0, y0, x1 - 1, y1 - 1), fill=col, width=3)
        d.line((x0, y1 - 1, x1 - 1, y0), fill=col, width=3)


def apply(spec_path, src, dst, preview=None):
    spec = json.load(open(spec_path, encoding="utf-8"))
    if open(src, "rb").read(4) == b"DDS ":
        import texture_text
        header, im, tail = texture_text.load_dds(src)
        d, off = None, None
    else:
        d, off, im = load_font_texture(src)
    font_path = os.path.join(FONT_DIR, spec.get("font", "bahnschrift.ttf"))
    for lab in spec["labels"]:
        box = lab["box"]
        clear_box(im, box, lab)
        if not lab["en"]:                 # blanked sprite
            continue
        tile = render_label(lab["en"], box[2] - box[0], box[3] - box[1], font_path,
                            lab.get("fill", spec.get("fill", [255, 255, 255])),
                            lab.get("outline", spec.get("outline", [0, 0, 0])),
                            lab.get("italic", False), lab.get("variation", spec.get("variation")))
        im.alpha_composite(tile, (box[0], box[1]))
    if d is None:
        texture_text.save_dds(dst, header, im, tail)
    else:
        r, g, b, a = im.split()
        raw = Image.merge("RGBA", (a, r, g, b)).tobytes()   # A,R,G,B byte order
        open(dst, "wb").write(d[:off] + raw + d[off + len(raw):])
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
