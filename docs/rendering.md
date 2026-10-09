# Rendering notes (Phase 2)

## First in-game test, 2026-10-08

Build: `ls000.bin` strings 248-251 replaced with English (opening monologue,
right after `（推力は３０％まで低下……。…）`). Deployed with `tools/deploy.py`.
Screenshots taken with RPCS3's F12 hotkey.

| Test | Result |
|---|---|
| Plain ASCII text | Renders with the game's own Latin glyphs |
| `@` | Line break, works with ASCII text; a following space shows as a small indent |
| `<tag>` | Angle brackets vanish, `tag` is shown: `<...>` is parsed as a control tag. Never emit ASCII `<` `>` |
| `[ ]`, `"`, `'`, `%`, `--`, `...` | Render correctly |
| Width | Every Latin glyph advances a full 32-px cell, so ~30 Latin characters fit per line. Text runs off the right edge |
| Wrapping | None. Lines only break at `@` |

## Font: `Common/Dat/Font/font.bin` ("FTTF")

```
0x00 "FTTF"  u32 file_size  u32 cell_w=0x20  u32 cell_h=0x20
0x10 u16 0x0100  u16 0x0300  u32 0x18180
0x54 page table: 256 x u32, index = codepoint >> 8, value = file offset of a
     page block (0 = page absent). 95 pages present: 00, 03, 04, 20-26, 30,
     33, 4E-9F, FF ...
page block: 256 x (u16 advance, u16 glyph_ref), index = codepoint & 0xFF
```

Sample entries:

| char | advance | glyph_ref |
|---|---|---|
| `A` | 0x16 (22) | 0x1E01 |
| `a` | 0x16 (22) | 0x1E02 |
| `i` | 0x16 (22) | 0x0603 |
| `.` | 0x12 (18) | 0x0B01 |
| `あ` | 0x20 (32) | 0x1F09 |
| `Ａ` | 0x20 (32) | 0x187A |

glyph_ref looks like (slot << 8 | sheet). ASCII is monospaced at 22 px in
the table, yet the renderer steps 32 px per glyph, so the advance field is
ignored (or overridden) by the text layout code. Fix options, in order of
preference:

1. Patch the layout routine in the EBOOT to use the table's advance.
2. Additionally rewrite ASCII advances in `font.bin` to real proportional
   widths (measured from the glyph bitmaps) once option 1 works.

The other font files (`exFont01..05.bin`) share the format.

## Next steps

- Locate the code that reads the FTTF page table (constant 0x54 offset,
  `lhz` of the advance) in `EBOOT.elf` with Ghidra/capstone.
- Find where the per-glyph x step is computed and the font-size setter.
- Find the line-width limit used by the message window, if any, to plan
  wrapping (manual `@` insertion by the build is the fallback).

## EBOOT advance patch, tested 2026-10-08

`tools/eboot_patch.py` (16 words; see `docs/eboot-renderer.md`) applied to
the pristine EBOOT.elf, deployed as EBOOT.BIN (RPCS3 boots the plain ELF; no
game-data reinstall needed for an EBOOT-only change). Result in the opening
monologue:

- Latin text now steps by the font table's advance (22 px for every ASCII
  letter), so a 49-character line (`ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklm
  0123456789`) fits on one dialogue line. `@` breaks still work.
- Capitals look right; lowercase shows gaps because narrow glyphs sit
  centred in a uniform 22 px advance. Next step: measure each ASCII glyph's
  ink width from the font bitmaps and write per-letter advances into
  `font.bin` (no further code change needed). fitcheck.py picks up the new
  widths automatically.
- Japanese text unaffected in the frames seen so far; still to check: menus,
  centred/right-aligned text, the battle screen and the scrolling text the
  renderer agent flagged (routine at 0x63060).

## Proportional font, tested 2026-10-08

`tools/fttf.py` (run by build.py) moves each ASCII glyph's ink to the left of
its cell and writes fitted advances. In game: sentences read naturally, the
two-line test wraps cleanly, Japanese lines are unchanged, and the full
alphabet line takes about two thirds of the box. Capitals sat slightly tight
with a 1 px gap, so the default gap is now 2 px (not yet re-checked in game).

## Full English build, tested 2026-10-09

All 84,516 translatable entries built and deployed (EBOOT text, menus, data
tables, Q&A, story, battle quotes). Observed in game:

- System dialogs (install prompts) and the scenario-select menu are in
  English and lay out correctly (centred text, italic headings, button hints).
- Story dialogue in both box types fits. The game draws text at about 0.81
  scale on screen, so the map-scene box (portrait on the left, ~700 screen
  px of text) holds about 865 font px; the LDBI budget of 832 px is safe.
- Speaker name boxes centre the English names; unit names ("Canis") show in
  the unit panel.
- The map command menu box fits about 9 letters, so 2-character Japanese
  commands do not need abbreviations. The first pass had squeezed short
  labels to the Japanese width ("Atk", "Spr", "Abl", stage titles like
  "God Stirs"); fitcheck/translate_batch now allow short labels 2.2x their
  Japanese width (min 160 px) and those 2,559 entries are being redone.
- Still unverified: library pages scrolling, intermission menus, battle
  screen and battle quotes, the stage-script words kept Japanese, and
  image-based text (title menu, legal notice, logos).
- Rebuilt with the relaxed label widths: the map command menu now reads
  Move / Attack / Ground / Spirit / Stats, with room to spare.
