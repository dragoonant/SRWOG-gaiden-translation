# EBOOT text renderer (FTTF fonts): reverse-engineering notes

Binary: `pristine/USRDIR/EBOOT.elf` (BLJS10133, decrypted). Big-endian ELF64, 32-bit pointers,
TOC (r2) = `0x00D5CAA8` for all code discussed here.

**Address mapping.** The code lives in PT_LOAD[0] (R+X, file 0x0 to 0xCDBA68, vaddr 0x10000).
**file offset = VA − 0x10000** for every code address in this document. `.text` covers
VA 0x10240 to 0xC3BD10.

Method: full capstone disassembly of `.text`, plus Ghidra 12.1.4 headless decompilation of the
functions below (language `PowerPC:BE:64:A2ALT-32addr`, r2 fixed to the TOC). Tools and
listings are in the session scratchpad, not in the repo.

## 1. Summary

* All FTTF glyph lookups happen in **six functions** (the only readers of the page-remap table
  at FTTF+0x454): two draw routines and four width-measure routines.
* The renderer has **two layout modes**, selected per draw by the byte **font+0xD4**:
  * **fixed** (0, the default after reset): each glyph is centred in a `size_w`-wide cell and
    the pen advances **`size_w`**.
  * **proportional** (1): the pen advances **`size_w / cell_w × entry.advance`**, glyphs are
    left-aligned, and the font's page-remap table is applied.
* `size_w` is the float at **font+0x2C**. Font reset (`0x005CCAE4`) sets it to **32.0f**
  (`lis r5,0x4200` at 0x005CCB14, stored at 0x005CCB24). Callers and the `<W=n>` tag change it
  through `SetSize` (`0x005CB970`). `cell_w` is the u32 at FTTF+0x08 (= 32).
  So in dialogue scale = 32/32 = 1.0 and the fixed step is exactly 32 px.
* Dialogue Latin text is drawn in fixed mode, which is why the advance field (22) has no effect.
  The table advance is not ignored by the engine as a whole: the proportional mode uses it.
* The patch (section 9) changes fixed mode so it advances `scale × entry.advance` and stops
  centring. That is 16 instruction words, with no code cave and no page remap. A 6-word
  alternative forces proportional mode instead.

## 2. Font object and FTTF data

Loading: `0x000181EC` calls `FontLoad(font = base+0x1B10, "Dat/Font/font.bin")` = `0x005CD768`.
This reads the file and calls `FontParse` (`0x005CCE98`). exFont01..05 are loaded in the loop at
0x00018224 (format string `%s/exFont%02d.bin`).

`FontParse` (`0x005CCE98`):

```c
if (*(u32*)data != 'FTTF') return 0;                 // lis 0x4654 / ori 0x5446 at 0x5CCEA0
font->hdr = data;                                    // font+0x10
tex = upload_texture(data + hdr->tex_off /*u32 @+0x14 = 0x18180*/ ...);
for (i = 0; i < 256; i++)                            // 0x5CD190..0x5CD254 (unrolled x8)
    if (hdr->page[i]) hdr->page[i] += (u32)data;     // page table @+0x54 becomes pointers
font->u_cell = cell_w / tex_w;   font->v_cell = cell_h / tex_h;   // +0x14, +0x18
font->u_px   = 1 / tex_w;        font->v_px   = 1 / tex_h;        // +0x1C, +0x20
font->u_off  = 0;                font->v_off  = font->v_px * 0.3; // +0x24, +0x28
```

Glyph entry (4 bytes, `page[cp>>8][cp&0xFF]`). The code reads it **byte-wise**:

| byte | meaning |
|---|---|
| +0 | never read (0 in every font) |
| +1 | **advance** in cell pixels. 0 means "no glyph" (the low byte of the u16 "advance") |
| +2 | texture column |
| +3 | texture row |

UVs: `u0 = col*u_cell + u_off`, `v0 = row*v_cell + v_off`, `u1 = (col+1)*u_cell - u_px`,
`v1 = (row+1)*v_cell - v_px`. The "glyph_ref" is (column, row) in the texture, not a slot/sheet
pair.

Page-remap table at FTTF+0x454: up to 8 entries of 6 bytes `{u16 src_page, u16 dst_page,
u16 add}`, terminated by a negative s16. It is used **only in proportional mode**.
font.bin contains `0030→00A0 +0` (kana use the narrow 22-px page A0) and `00FF→0000 +0x20`
(U+FF01..FF5E full-width forms use the ASCII glyphs). The exFonts have an empty table.

Font object fields used by the text code:

| offset | type | meaning |
|---|---|---|
| +0x10 | ptr | FTTF header |
| +0x14..+0x28 | float | UV constants (above) |
| +0x2C / +0x30 | float | **size_w / size_h** (glyph quad size in px; reset = 32.0) |
| +0x34 | s32 | max line width for squeeze-to-fit, −1 = off (reset = −1) |
| +0x40..+0x7C | 4×vec4 | quad corner template written by SetSize |
| +0x80..+0xB0 | 4×vec4 | vertex colours |
| +0xD4 | u8 | **layout mode: 0 fixed, 1 proportional** (reset = 0) |
| +0xD5 | s8 | italic shear in percent of size_w (`<T=n>`) |

## 3. Font size and scale

`SetSize(font, f1 = w, f2 = h)` = **`0x005CB970`** (leaf):

```c
font->size_w = w;  font->size_h = h;                          // +0x2C, +0x30
shear = (s8)font->shear_pct * 0.01f /*TOC+0x20B0*/ * w;
font->q[0] = {shear, 0};  font->q[1] = {0, h};                // +0x40, +0x50
font->q[2] = {w + shear, 0};  font->q[3] = {w, h};            // +0x60, +0x70
```

Inside each draw/measure routine: **`scale = font->size_w / (float)hdr->cell_w`**
(draw A 0x00A125DC `fdivs f27,f13,f0`; draw B 0x00A14BCC `fdivs f28,…`; measure routines
`fdivs f12,f13,f0`). The glyph quad is always `size_w × size_h`. Only the pen step differs
between the modes.

Squeeze-to-fit: if `font+0x34 >= 0` and the measured width is greater than it, the draw routines
recompute `scale = max_w/width × size_w / cell_w`. Setup is at 0x00A13A2C (A) and 0x00A16EAC (B).
The fixed loop then uses a uniform step of `size_w × max_w / width`.

## 4. UTF-8 decode (inlined in all six routines)

```c
c = s[0];
if ((c & 0xE0) == 0xE0) { cp = (c&0x0F)<<12 | (s[1]&0x3F)<<6 | (s[2]&0x3F); n = 3; }
else if (c & 0x80)      { cp = (c&0x1F)<<6  | (s[1]&0x3F);                  n = 2; }
else                    { cp = c;                                            n = 1; }
```

Example: draw A at 0x00A12760..0x00A12790, with the 3-byte path at 0x00A1311C and the 2-byte
path at 0x00A13278. 4-byte sequences are not supported (F0..F7 are treated as 3-byte), and the
BMP is the limit. `0x005CDF10` returns the byte offset of the Nth character (same rule).

## 5. Glyph lookup (inlined)

```c
page = cp >> 8;
if (font->prop) {                                   // fixed mode skips this block
    for (k = 0; k < 8 && (s16)hdr->remap[k].src >= 0; k++)       // lhz 0x454+6k
        if ((hdr->remap[k].src & 0xFF) == page) {
            page = hdr->remap[k].dst & 0xFF;  cp += hdr->remap[k].add & 0xFF;  break; }
}
blk = hdr->page[page];                 // slwi 2; addi 0x50; lwz 4(...) = *(hdr+0x54+page*4)
e   = blk ? blk + (cp & 0xFF)*4 : 0;   // rlwinm rX,cp,2,22,29
if (!e || e[1] == 0) -> "missing glyph"
```

Example sites in draw A: proportional loop 0x00A1279C..0x00A128C4, fixed loop
0x00A132EC..0x00A1331C.

## 6. Draw routines

| | entry (VA / file) | wrapper | used by |
|---|---|---|---|
| **draw A** | `0x00A123F0` / 0xA023F0 | `0x005CE174` | tagged text: per-segment drawing in 0x005CEBCC / 0x005CF308 (called by the tag layout 0x005D2120) |
| **draw B** | `0x00A149E4` / 0xA049E4 | `0x005CE1A0` (via `0x005CEB3C`, 71 callers, and 0x005CE1DC) | plain text without `<` (e.g. the text window 0x005D2D54 calls 0x005CEB3C when a line has no `<`, otherwise 0x005D2120) |

Signature (both): `draw(f1 x, f2 y, r3 font, r4 str, r5 &end, r6.., r8 outline_pass, r9 ..)`.
Draw B is a copy of A with different register allocation (scale in f28 and squeeze step in
f27, where A has scale in f27 and squeeze step in f28). Each glyph is emitted as a quad by
`0x00A11A58`.

```c
float scale = font->size_w / hdr->cell_w;           // A:f27  B:f28
float pen = 0;                                      // f30
squeezed = font->max_w >= 0 && measure(str,end) > font->max_w;   // flag at 0x114(r1)
if (squeezed) { scale = (max_w/width) * size_w / cell_w; ... }
if (font->prop == 0) {                              // A 0xA126F8 lbz r0,0xD4(r31) -> 0xA13294
  for (each cp) {                                   // FIXED loop, A 0xA132A0.., B 0xA1586C..
    e = lookup(cp);                                 // no remap
    if (!e || e[1]==0) { emit_blank(); pen += squeezed ? step : font->size_w; continue; }
                                                    // A 0xA133AC..0xA133C0
    gx = x + pen + scale * (cell_w - e[1]) * 0.5f;  // A 0xA13AD0..0xA13B1C  (centring)
    uv from e[2], e[3]; emit_quad(gx, y, ...);      // (+4 extra quads if outline_pass)
    if (squeezed) pen += step;                      // step = size_w*max_w/width (A 0xA13BC0..0xA13BF0)
    else          pen += font->size_w;              // A 0xA13E54/0xA13E58 (outline: 0xA1496C/0xA14970)
  }
} else {
  for (each cp) {                                   // PROPORTIONAL loop, A 0xA12744..
    remap + lookup;
    missing -> pen += squeezed ? f28 : size_w;      // A 0xA12954..0xA12968
    gx = x + pen;  emit_quad(...);
    pen += scale * e[1];                            // A 0xA13270 fmadds f30,f27,f26,f30
  }                                                 //   (squeezed: 0xA12B0C/0xA12B18)
}
```

### Where the 32-px step comes from (unpatched, fixed mode)

| site | A (VA) | B (VA) | instructions |
|---|---|---|---|
| normal glyph | 0x00A13E54, 0x00A13E58 | 0x00A16378, 0x00A1637C | `lfs f0,0x2C(r31)` / `fadds f30,f30,f0` |
| normal glyph, outline pass | 0x00A1496C, 0x00A14970 | 0x00A16E90, 0x00A16E94 | `lfs f6,0x2C(r31)` / `fadds f30,f30,f6` |
| missing glyph / advance 0 | 0x00A133BC, 0x00A133C0 | 0x00A1597C, 0x00A15980 | same pattern |
| squeezed | 0x00A13BC0..0x00A13BF0, 0x00A13EA0 | 0x00A160E4..0x00A16114, 0x00A163C4 | `size_w*max/width` |
| centring | 0x00A13AD0 (`lfs f2,0x2160(r2)` = 0.5), 0x00A13AD8, 0x00A13B18, 0x00A13B1C | 0x00A15FF4, 0x00A15FFC, 0x00A1603C, 0x00A16040 | `(cell_w-adv)*0.5*scale` |

`f0` here is **font+0x2C = size_w**. It is not a code constant and not the header's cell_w.
The 32 comes from the font-reset default 32.0f, or from whatever size the caller or `<W=n>`
set. The entry's advance byte is read in fixed mode only to centre the glyph.

## 7. Measure routines

| entry (VA) | wrapper | stops at | note |
|---|---|---|---|
| `0x00A11F28` | `0x005CDEBC` | end pointer | used for segment widths in tagged text and by the draw routines' squeeze test |
| `0x00A12190` | `0x005CDEE8` (13 callers) | NUL | |
| `0x00A11CB8` | `0x005CDE94` | NUL | skips U+0020..U+0080 (counts non-ASCII only) |
| `0x00A16F94` | `0x005CEBA0` | end pointer | skips U+0020..U+0080 |

```c
float w = 0, scale = font->size_w / hdr->cell_w;    // f1, f12, f13 = size_w
for (each cp) {
    if (font->prop) remap(...);                     // flag re-read every iteration
    blk = hdr->page[page];
    if (blk) w += font->prop ? scale * blk[cp&0xFF].adv   // fmadds f1,f12,f3,f1
                             : font->size_w;              // fadds  f1,f1,f13
}
return w;
```

Fixed/proportional branch: 0x00A11E60, 0x00A120D0, 0x00A12328, 0x00A1714C (`beq` to the
`fadds f1,f1,f13` at 0x00A11EE4, 0x00A12134, 0x00A12394, 0x00A171C8).

## 8. Text layout, '@' and tags

**Tag layout `0x005D2120`** (59 callers): `(f1 x, f2 y, f3 ?, r3 font, r4 str)` works on a
segment state at 0x80(r1). Roughly (the decompiler output for this loop is messy, so treat
this as an outline):

```c
while (*s) {
    lt = strchr(s, '<');                                   // 0x5D2278
    if (!lt) { if (DrawLine(font,&seg) /*0x5CEBCC*/) ...; continue; }
    if (text before lt) DrawSpan(font,&seg);               // 0x5CF308 (to seg.end)
    c = lt[1];
    if ((u8)(c - '/') > 0x2A) return 0.0f;                 // unknown tag: stop the line
    switch (c) { /* jump table at *(TOC+0x21CC) = 0x5D22E4 */ }
}
```

`DrawLine` (0x005CEBCC) / `DrawSpan` (0x005CF308) find the next `@` or NUL (or the segment end).
They call SetSize(seg.w, seg.h) on this font and on two auxiliary font objects (pointers at
global+0x164 / +0x168), then draw with **draw A**: once, or twice when the `<B>`/`<D>` pass
is active. They then advance `seg.pen_x += measure(span)`
with `0x00A11F28`. On `@`: `if (seg.advance_y) seg.y += seg.h + seg.line_gap; seg.pen_x = 0;
s++`. So `@` is the line break, and there is no automatic wrapping anywhere in this path. A
generic line splitter used by text boxes (around 0x00088080..0x00088460) also splits on `@`
and `\n`.

Tag handlers (`r3 = font, r4 = &seg`, `seg.p` at +0x78 points at the letter). Numbers are
parsed by 0x005CB2E8 (`strtol(p,0,10)` up to `>`) or 0x005CB21C (base 16):

| tag | handler | effect (segment field) |
|---|---|---|
| `</…>` | 0x005CABD8 | close/pop |
| `<W=n>` | 0x005CB760 | **glyph width = n px** (+0x80, passed to SetSize, so it is also the fixed step) |
| `<H=n>` | 0x005CB664 | glyph height (+0x84), raises the line height |
| `<S=n>` | 0x005CB810 | **pen_x += n × W / 32** (+0x70; TOC+0x20AC = 1/32): manual spacing |
| `<X=n>` / `<Y=n>` | 0x005CB5C8 / 0x005CB4E0 | x / y offset (+0x2C / +0x30) |
| `<T=n>` | 0x005CB8D4 | italic shear % (byte +0x20 → font+0xD5) |
| `<B>` / `<D>` | 0x005CB1A8 / 0x005CB134 | flags +0x1D / +0x1E (outline/shadow passes) |
| `<L=n>` / `<LINK=n>` | 0x005CB3B4 | line gap (+0x08) / link id |
| `<N…>` | 0x005CB9FC | number fields (`NR=`, `NR0..2=`) |
| `<I=n>` | 0x005D1908 | icon |
| A, C, F, P, Q, R, U | 0x005CC068, 0x005CC8FC, 0x005CC6D4, 0x005D1498, 0x005D1094, 0x005D034C, 0x005D0C88 | not analysed |

`<W=63>　</W>` therefore draws U+3000 with a 63-px quad and a 63-px step.

Caveat: an unknown tag letter makes 0x005D2120 return, which would drop the rest of the line.
The playtest note (brackets vanish, the tag text is shown) does not match that exactly. Either
the opening monologue goes through another text path, or the test string used a letter with a
handler. Recheck with a known-unknown tag such as `<Z>` if it matters.

Who chooses the mode: the reset at 0x005CCAE4 sets `font+0xD4 = 0`. Some callers set it to 1,
for example the text window 0x005D2D54 (`prop = (win+0x1D0 != 0)` at 0x005D2EAC / 0x005D3244),
or force it per draw (0x00063464 stores 0, 0x000634C4 stores 1).

## 9. Patch: fixed mode advances by the table advance

Implemented in `tools/eboot_patch.py` (default `--variant advance`). Idea: in the fixed loop,
convert `entry.advance` where the code converted `cell_w − advance`, compute
`step = scale × advance` into the register the squeezed path already uses for its step (A: f28,
B: f27), stop centring, and add that register to the pen. In the measure routines, always take
the `scale × advance` branch. The mode flag still gates the page remap, so Japanese glyphs are
looked up exactly as before.

`step` uses the same `scale = size_w / cell_w` that produces the 32. With size 32 and
`'A'` (advance 22) the step is 22 px, and `<W=n>` scales it.

| # | VA | file off | original | new | |
|---|---|---|---|---|---|
| A1 | 0x00A13AD8 | 0xA03AD8 | `7F692050` subf r27,r9,r4 | `7D3B4B78` mr r27,r9 | f8 becomes (float)advance instead of cell_w−advance |
| A2 | 0x00A13B1C | 0xA03B1C | `ECDB307A` fmadds f6,f27,f1,f6 | `EF9B0232` fmuls f28,f27,f8 | no centring offset; f28 = scale×advance |
| A3 | 0x00A13BC0 | 0xA03BC0 | `C39F002C` lfs f28,0x2C(r31) | `60000000` nop | squeezed: keep f28 |
| A4 | 0x00A13BE4 | 0xA03BE4 | `EF8D0732` fmuls f28,f13,f28 | `60000000` nop | squeezed: keep f28 (scale is already the squeezed scale) |
| A5 | 0x00A13E58 | 0xA03E58 | `EFDE002A` fadds f30,f30,f0 | `EFDEE02A` fadds f30,f30,f28 | pen += scale×advance |
| A6 | 0x00A14970 | 0xA04970 | `EFDE302A` fadds f30,f30,f6 | `EFDEE02A` fadds f30,f30,f28 | same, outline-pass path |
| B1 | 0x00A15FFC | 0xA05FFC | `7D49D850` subf r10,r9,r27 | `7D2A4B78` mr r10,r9 | as A1 |
| B2 | 0x00A16040 | 0xA06040 | `ECDC307A` fmadds f6,f28,f1,f6 | `EF7C0232` fmuls f27,f28,f8 | as A2 |
| B3 | 0x00A160E4 | 0xA060E4 | `C37F002C` lfs f27,0x2C(r31) | `60000000` nop | as A3 |
| B4 | 0x00A16108 | 0xA06108 | `EF6D06F2` fmuls f27,f13,f27 | `60000000` nop | as A4 |
| B5 | 0x00A1637C | 0xA0637C | `EFDE002A` fadds f30,f30,f0 | `EFDED82A` fadds f30,f30,f27 | as A5 |
| B6 | 0x00A16E94 | 0xA06E94 | `EFDE302A` fadds f30,f30,f6 | `EFDED82A` fadds f30,f30,f27 | as A6 |
| M1 | 0x00A11E60 | 0xA01E60 | `419E0084` beq cr7,… | `60000000` nop | measure 0xA11CB8 |
| M2 | 0x00A120D0 | 0xA020D0 | `419E0064` beq cr7,… | `60000000` nop | measure 0xA11F28 |
| M3 | 0x00A12328 | 0xA02328 | `4182006C` beq … | `60000000` nop | measure 0xA12190 |
| M4 | 0x00A1714C | 0xA0714C | `4186007C` beq cr1,… | `60000000` nop | measure 0xA16F94 |

Register safety (checked in the listings):

* r27 (A) and r10 (B) are temporaries used only for the int-to-float conversion.
* f28 (A) and f27 (B) are callee-saved. Outside the squeezed path they are read only by the
  squeezed and missing-glyph branches. Neither is written between the new definition and the
  pen update on the normal or outline paths, and `0x00A11A58` preserves them under the ABI.
* The `fmuls f1,f8,f2` left at 0x00A13B18 / 0x00A1603C is now dead.

Side effects of the default variant, all in fixed mode:

* Glyphs whose advance is not 32 lose their centring and use their advance. Besides ASCII
  (mostly 22, digits and `,-.` 18, a few 20/23) this covers Greek U+0391.. (28) and
  `― ‘ ’ “ ” ‥ … ′ ″ ※` and `∞ ∥ ∴ ≠ ≦ ≧ ≪ ≫` (28). Japanese full-width kana and kanji (32) are unchanged.
* Squeezed lines now shrink proportionally, which matches the new measurement.
* The missing-glyph step (size_w) is unchanged. A glyph with advance 0 is counted as 0 by the
  measure routines, as it already was in proportional mode.

**Alternative (`--variant flag`, 6 words):** replace the mode-byte load with `li rX,1` at
0x00A11D2C (`898300D4`→`39800001`), 0x00A11F9C (`88C300D4`→`38C00001`), 0x00A121F4
(`88C300D4`→`38C00001`), 0x00A126F8 (`881F00D4`→`38000001`), 0x00A14CCC
(`8BDF00D4`→`3BC00001`) and 0x00A17018 (`88A300D4`→`38A00001`). This uses the developers'
own proportional loop, but it also enables the page remap. Kana switch to the narrow page A0,
and full-width Ａ１！ etc. render as the ASCII glyphs. Do not combine the two variants.

After either patch, the advance byte (+1) of each entry in font.bin is the real advance. Edit
those bytes to set proportional ASCII widths (space is currently 22).

## 10. Free space (code cave)

Not needed for the patches above.

* `.text` has no zero run of 32 bytes or more.
* PT_LOAD[0] (R+X) ends at file 0xCDBA68. The file has **0x4598 zero bytes of padding** after
  it (file 0xCDBA68..0xCE0000 = **VA 0x00CEBA68..0x00CF0000**). The next segment starts at VA
  0xCF0000. That area is not loaded today. To use it, raise phdr[0] `p_filesz` (file 0x60) and
  `p_memsz` (file 0x68) from 0xCDBA68 to 0xCE0000. It is reachable with `b`/`bl` from
  0x00A1xxxx (distance about 2.9 MB, under ±32 MB). This is the recommended cave if one is ever
  needed.
* Zero runs inside the rodata part of the same segment (VA 0x00C44D80 len 0x2B7,
  0x00C45378 len 0x1F8, 0x00C46714 len 0x1DA; no u32 pointers to them were found) might be
  usable, but they could be zero-initialised tables. They are not verified, so avoid them.

## 11. Open points to verify in game

1. With the patch, dialogue Latin advances 22 px (18 for `. , -` and digits), and Japanese lines
   look unchanged apart from the 28-px punctuation listed above.
2. Centred or right-aligned UI strings (these use the measure routines) still line up, and
   squeezed labels in narrow boxes still fit.
3. Outlined or shadowed text (outline pass, A6/B6) spaces the same as normal text.
4. `0x00063060` (descriptor 0x00D0C730) positions substrings by **character index × a fixed
   width** (`fmadds f28,f5,f31,f13` at 0x00063258, using 0x005CDF10). It looks like a
   scrolling or marquee text. Any text that goes through it stays index-based and may look
   wrong with proportional glyphs.
5. Cursor or arrow placement after a message, if a caller computes it from the character count.
