#!/usr/bin/env python3
"""FTTF game font: glyph table, DXT5 texture, per-glyph advances.

Layout (see docs/rendering.md, docs/eboot-renderer.md):
  0x00 "FTTF"  u32 file_size  u32 cell_w  u32 cell_h  u16 ?  u16 ?  u32 tex_off
  0x54 page table, 256 x u32 offsets (index = codepoint >> 8)
  page block: 256 x 4 bytes {0, advance, column, row} (index = codepoint & 0xFF)
  tex_off: texture container
     +0x00 u32 version  +0x04 u32 data size  +0x08 u32 count
     +0x0C u32 id  +0x10 u32 data offset (from tex_off)  +0x14 u32 size
     +0x18 CellGcmTexture: u8 format (0x88 = DXT5), u8 mipmaps, u8 dim,
           u8 cube, u32 remap, u16 width, u16 height, ...
  The texture is DXT5, blocks in plain raster order.

The renderer (with tools/eboot_patch.py) draws each glyph's full cell at
the pen position and then advances the pen by the glyph's advance, so a
letter's left bearing comes from where its ink sits inside the cell.

Commands:
  preview FONT OUT.png [first_cp last_cp]   render glyph cells to a PNG
  measure FONT                              ink box of each ASCII glyph
  proportional FONT OUT [--gap N] [--space N] [--left N]
        move every printable-ASCII glyph's ink to N px from its cell's left
        edge (default 0), set advance = ink width (alpha >= --thr, default
        128) + gap (default 2), space = --space (default 8); digits share the
        widest digit's advance.
"""
import struct
import sys
import zlib

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class Font:
    def __init__(self, path):
        self.d = bytearray(open(path, "rb").read())
        if self.d[:4] != b"FTTF":
            raise ValueError("not FTTF")
        self.cell_w, self.cell_h = struct.unpack_from(">II", self.d, 8)
        self.tex_off = struct.unpack_from(">I", self.d, 0x14)[0]
        t = self.tex_off
        data_rel = struct.unpack_from(">I", self.d, t + 0x10)[0]
        self.fmt = self.d[t + 0x18]
        self.tw, self.th = struct.unpack_from(">HH", self.d, t + 0x20)
        self.dxt3 = (self.fmt & 0x9F) == 0x87          # 0xA7 = DXT3, linear
        if self.fmt not in (0x88, 0xA8) and not self.dxt3:
            raise ValueError("texture format 0x%02X not DXT3/DXT5" % self.fmt)
        self.data = t + data_rel
        self.bw = self.tw // 4          # blocks per texture row

    # glyph table --------------------------------------------------------
    def entry_off(self, cp):
        blk = struct.unpack_from(">I", self.d, 0x54 + 4 * (cp >> 8))[0]
        return blk + 4 * (cp & 0xFF) if blk else None

    def glyph(self, cp):
        o = self.entry_off(cp)
        if o is None or self.d[o + 1] == 0:
            return None
        return self.d[o + 1], self.d[o + 2], self.d[o + 3]   # advance, col, row

    def set_advance(self, cp, adv):
        self.d[self.entry_off(cp) + 1] = adv

    # DXT5 ---------------------------------------------------------------
    def block_off(self, bx, by):
        return self.data + 16 * (by * self.bw + bx)

    @staticmethod
    def decode_block_dxt3(b):
        alpha = [((b[i // 2] >> (4 * (i % 2))) & 0xF) * 17 for i in range(16)]
        c0, c1 = struct.unpack_from("<HH", b, 8)

        def rgb(c):
            return ((c >> 11) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31)
        p0, p1 = rgb(c0), rgb(c1)
        pal = [p0, p1, tuple((2 * x + y) // 3 for x, y in zip(p0, p1)), tuple((x + 2 * y) // 3 for x, y in zip(p0, p1))]
        cbits = struct.unpack_from("<I", b, 12)[0]
        return [pal[(cbits >> (2 * i)) & 3] + (alpha[i],) for i in range(16)]

    @staticmethod
    def decode_block(b):
        a0, a1 = b[0], b[1]
        if a0 > a1:
            al = [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
        else:
            al = [a0, a1] + [((5 - i) * a0 + i * a1) // 5 for i in range(1, 5)] + [0, 255]
        abits = int.from_bytes(b[2:8], "little")
        alpha = [al[(abits >> (3 * i)) & 7] for i in range(16)]
        c0, c1 = struct.unpack_from("<HH", b, 8)

        def rgb(c):
            return ((c >> 11) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31)
        p0, p1 = rgb(c0), rgb(c1)
        pal = [p0, p1, tuple((2 * x + y) // 3 for x, y in zip(p0, p1)), tuple((x + 2 * y) // 3 for x, y in zip(p0, p1))]
        cbits = struct.unpack_from("<I", b, 12)[0]
        return [pal[(cbits >> (2 * i)) & 3] + (alpha[i],) for i in range(16)]

    @staticmethod
    def encode_block(px):
        """px: 16 RGBA tuples. Simple DXT5 encoder adequate for glyph art."""
        alphas = [p[3] for p in px]
        amax, amin = max(alphas), min(alphas)
        if amax == amin:
            a0, a1, idx = amax, amin, [0] * 16
        else:
            a0, a1 = amax, amin                       # 8-value mode (a0 > a1)
            pal = [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
            idx = [min(range(8), key=lambda k: abs(pal[k] - a)) for a in alphas]
        abits = 0
        for i, k in enumerate(idx):
            abits |= k << (3 * i)
        # colour: weighted by alpha; glyphs are near-monochrome
        vis = [p for p in px if p[3] > 0] or px
        lum = lambda p: 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]
        hi, lo = max(vis, key=lum), min(vis, key=lum)

        def to565(p):
            return ((p[0] * 31 + 127) // 255) << 11 | ((p[1] * 63 + 127) // 255) << 5 | ((p[2] * 31 + 127) // 255)
        c0, c1 = to565(hi), to565(lo)
        if c0 < c1:
            c0, c1, hi, lo = c1, c0, lo, hi
        if c0 == c1:
            cbits = 0
        else:
            pal = [hi, lo, tuple((2 * x + y) / 3 for x, y in zip(hi, lo)), tuple((x + 2 * y) / 3 for x, y in zip(hi, lo))]
            cbits = 0
            for i, p in enumerate(px):
                k = min(range(4), key=lambda j: sum((a - b) ** 2 for a, b in zip(pal[j], p[:3])))
                cbits |= k << (2 * i)
        return bytes([a0, a1]) + abits.to_bytes(6, "little") + struct.pack("<HHI", c0, c1, cbits)

    def read_cell(self, col, row):
        """Return cell_h rows of cell_w RGBA tuples."""
        w, h = self.cell_w, self.cell_h
        img = [[None] * w for _ in range(h)]
        bx0, by0 = col * w // 4, row * h // 4
        for by in range(h // 4):
            for bx in range(w // 4):
                o = self.block_off(bx0 + bx, by0 + by)
                blk = self.d[o:o + 16]
                pix = self.decode_block_dxt3(blk) if self.dxt3 else self.decode_block(blk)
                for i, p in enumerate(pix):
                    img[by * 4 + i // 4][bx * 4 + i % 4] = p
        return img

    def write_cell(self, col, row, img):
        w, h = self.cell_w, self.cell_h
        bx0, by0 = col * w // 4, row * h // 4
        for by in range(h // 4):
            for bx in range(w // 4):
                px = [img[by * 4 + i // 4][bx * 4 + i % 4] for i in range(16)]
                o = self.block_off(bx0 + bx, by0 + by)
                self.d[o:o + 16] = self.encode_block(px)

    def save(self, path):
        open(path, "wb").write(bytes(self.d))


def ink_box(img, thr=40):
    xs = [x for y in range(len(img)) for x in range(len(img[0])) if img[y][x][3] > thr]
    return (min(xs), max(xs)) if xs else None


def write_png(path, rows):
    """rows: list of lists of (r, g, b) tuples."""
    h, w = len(rows), len(rows[0])
    raw = b"".join(b"\0" + bytes(c for p in r for c in p) for r in rows)
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    open(path, "wb").write(png)


def preview(font, cps, cols=16, scale=2):
    cw, ch = font.cell_w, font.cell_h
    rows_n = (len(cps) + cols - 1) // cols
    W, H = cols * cw * scale, rows_n * ch * scale
    canvas = [[(40, 40, 60)] * W for _ in range(H)]
    for n, cp in enumerate(cps):
        g = font.glyph(cp)
        if not g:
            continue
        adv, col, row = g
        img = font.read_cell(col, row)
        ox, oy = (n % cols) * cw * scale, (n // cols) * ch * scale
        for y in range(ch):
            for x in range(cw):
                a = img[y][x][3]
                c = (a, a, a) if x < adv else (a // 2, 40 + a // 3, 40)
                if x == adv:
                    c = (200, 60, 60)
                for sy in range(scale):
                    for sx in range(scale):
                        canvas[oy + y * scale + sy][ox + x * scale + sx] = c
    return canvas


# pixels to move each glyph down (negative = up); default for others is -1
DESCENDER_DROP = {"g": 2, "j": 2, "p": 2, "q": 2, "y": 2, ",": 0, ";": 0}


def free_cell(f):
    """An empty texture cell that no glyph entry references (searched from the
    bottom of the texture up)."""
    used = set()
    for page in range(256):
        blk = struct.unpack_from(">I", f.d, 0x54 + 4 * page)[0]
        if blk:
            for i in range(256):
                o = blk + 4 * i
                if f.d[o + 1]:
                    used.add((f.d[o + 2], f.d[o + 3]))
    cols, rows = f.tw // f.cell_w, f.th // f.cell_h
    for row in range(rows - 1, -1, -1):
        for col in range(cols - 1, -1, -1):
            if (col, row) in used:
                continue
            img = f.read_cell(col, row)
            if all(p[3] == 0 for r in img for p in r):
                return col, row
    raise ValueError("no free glyph cell")


def with_diaeresis(base, thr=128):
    """Return a copy of a processed lowercase glyph with two dots drawn above
    its x-height (the game font has no diaeresis to borrow)."""
    h, w = len(base), len(base[0])
    ink = [(x, y) for y in range(h) for x in range(w) if base[y][x][3] > thr]
    top = min(y for _, y in ink)
    xs = [x for x, _ in ink]
    cx = (min(xs) + max(xs)) / 2
    colour = next(base[y][x] for x, y in ink)[:3]
    out = [list(r) for r in base]
    dot_w, dot_h, gap = 4, 4, 4
    y0 = max(0, top - dot_h - 2)
    for left in (round(cx - gap / 2 - dot_w), round(cx + gap / 2)):
        for y in range(y0, y0 + dot_h):
            for x in range(left, left + dot_w):
                corner = (y in (y0, y0 + dot_h - 1)) and (x in (left, left + dot_w - 1))
                a = 110 if corner else 255
                if 0 <= x < w and a > out[y][x][3]:
                    out[y][x] = colour + (a,)
    return out


def add_umlauts(f, thr=128):
    """ä: redraw its cell as a + dots. ü: compose u + dots in a free cell and
    add the U+00FC entry (Lüne, Wildwürger; Sänger, Rätsel)."""
    ga, gä, gu = f.glyph(0x61), f.glyph(0xE4), f.glyph(0x75)
    f.write_cell(gä[1], gä[2], with_diaeresis(f.read_cell(ga[1], ga[2]), thr))
    f.d[f.entry_off(0xE4) + 1] = f.d[f.entry_off(0x61) + 1]
    col, row = free_cell(f)
    f.write_cell(col, row, with_diaeresis(f.read_cell(gu[1], gu[2]), thr))
    o = f.entry_off(0xFC)
    f.d[o:o + 4] = bytes([0, f.d[f.entry_off(0x75) + 1], col, row])


def make_proportional(f, gap=2, space=8, left=0, thr=128, write=True):
    """Move each printable-ASCII glyph's ink to `left` px from its cell edge
    and set advance = ink width + gap. Returns {codepoint: advance}. With
    write=False only the advances are computed (used by fitcheck.py)."""
    adv = {}
    for cp in range(0x21, 0x7F):
        g = f.glyph(cp)
        if not g:
            continue
        img = f.read_cell(g[1], g[2])
        box, full = ink_box(img, thr), ink_box(img, 8)
        if not box:
            continue
        x0, x1 = box
        x0 = max(full[0], x0 - 1)          # keep the faint left edge inside the cell
        shift = x0 - left
        # Vertical: the original font sits every glyph on row 29, so g/j/p/q/y
        # float with no descender. Raise everything else 1 px (baseline row 28)
        # and drop the descender letters 2 px (tails to row 31). Commas and
        # semicolons stay put so they dip just below the baseline.
        dy = DESCENDER_DROP.get(chr(cp), -1)
        if (shift or dy) and write:
            blank = (img[0][0][0], img[0][0][1], img[0][0][2], 0)
            h, w = len(img), len(img[0])
            img = [[img[y - dy][x + shift] if 0 <= y - dy < h and 0 <= x + shift < w else blank
                    for x in range(w)] for y in range(h)]
            f.write_cell(g[1], g[2], img)
        adv[cp] = left + (x1 - x0 + 1) + gap
    if 0x75 in adv and 0x61 in adv:      # ä, ü = a, u + drawn dots
        adv[0xE4], adv[0xFC] = adv[0x61], adv[0x75]
        if write:
            add_umlauts(f, thr)
    digits = [adv[c] for c in range(0x30, 0x3A) if c in adv]
    for c in range(0x30, 0x3A):
        if c in adv:
            adv[c] = max(digits)
    adv[0x20] = space
    for cp, a in adv.items():
        adv[cp] = min(a, f.cell_w)
        if write:
            f.set_advance(cp, adv[cp])
    return adv


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "preview":
        f = Font(argv[2])
        a, b = (int(argv[4], 0), int(argv[5], 0)) if len(argv) > 5 else (0x20, 0x7E)
        write_png(argv[3], preview(f, list(range(a, b + 1))))
        print("wrote", argv[3])
    elif cmd == "measure":
        f = Font(argv[2])
        for cp in range(0x21, 0x7F):
            g = f.glyph(cp)
            if g:
                box = ink_box(f.read_cell(g[1], g[2]))
                print("%s adv=%d col=%d row=%d ink=%s" % (chr(cp), g[0], g[1], g[2], box))
    elif cmd == "proportional":
        f = Font(argv[2])
        opt = lambda k, d: int(argv[argv.index(k) + 1]) if k in argv else d
        adv = make_proportional(f, opt("--gap", 2), opt("--space", 8), opt("--left", 0), opt("--thr", 128))
        f.save(argv[3])
        print("wrote %s; advances: %s" % (argv[3], " ".join("%s%d" % (chr(c), a) for c, a in sorted(adv.items()))))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
