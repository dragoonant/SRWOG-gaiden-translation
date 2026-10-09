# SRW OG Gaiden (PS2, SLPS-25836) English Translation: Course of Action

## 0. Reality check before starting

A complete, playable English patch for OG Gaiden already exists:
**camd11/srw-og-gaiden-en** (author "Creamhouse", v0.2.9, first released June 2026).
It was built the same way you are proposing: Claude for reverse engineering, translation
and tooling, Codex for pixel art. It ships only an xdelta patch, not its tools or script dump.
It has 12 open issues and a list of known defects (garbled footer button hints, blank Arado
battle quotes, a second BGM list untranslated, truncated backlog rows, a real-hardware freeze
in the stage 2 intro, a stray `#` in CONTINUE, overlapping Spirit legend icons, Limited Edition
disc unsupported).

Three honest options:

1. **Independent rebuild (the "cut my teeth" option).** You learn the whole pipeline. Their
   changelog is a free map of every landmine they hit. This plan assumes this option.
2. **Contribute to camd11's project.** Fastest route to shipping something, but without their
   tools you would still have to rebuild extraction and reinsertion to fix anything beyond
   what xdelta diffs expose.
3. **Pick a different, untranslated PS2 SRW** (MX, Alpha 2, Alpha 3, Scramble Commander 2) and
   reuse everything from this plan. Same engine family, no duplicate effort.

Whichever you choose, the pipeline below is the same.

## 1. Legal and repo hygiene (day 1)

- Dump your own retail disc. Verify against the redump checksums
  (4,666,294,272 bytes; camd11 README lists MD5/SHA1 for the standard SLPS-25836 disc).
- **Never commit game data.** The repo holds tools, the extracted script as text, the
  translation, font/art sources you drew, and the final xdelta. Add a `.gitignore` for
  `*.iso`, `*.bin`, `*.BIN`, `*.elf`, `extracted/`, `build/`.
- Patch format: xdelta3 against the verified ISO, same-size in-place edits where possible
  so it works on real hardware (OPL/FreeMcBoot) and PCSX2 alike.

## 2. Workstation setup

| Need | Tool |
|---|---|
| Emulator with debugger | PCSX2 (nightly). Built-in R5900 debugger, memory view, breakpoints, save states |
| ISO in/out | 7-Zip or `isoinfo`/`pycdlib` to pull files; for reinsertion edit in place by LBA, or rebuild with `mkisofs -udf` only if you have to grow files |
| Disassembly | Ghidra with the PS2 EE loader (ghidra-emotionengine-reloaded) for the boot ELF `SLPS_258.36` |
| Hex | ImHex or 010 Editor |
| Archive poking | QuickBMS (generic), plus your own Python scripts (this is where most of the work is) |
| Assembly patches | armips for ELF code patches (camd11 credits the "xdelta/armips lineage") |
| Images | Python + Pillow for TIM2/raw swizzled textures; Aseprite or GIMP for the redraws |
| Text | Python 3, Shift-JIS codec, a glossary file, and an LLM for first-pass translation |

## 3. Reconnaissance (week 1)

Goal: know where every byte of displayed text lives.

1. Pull the file tree out of the ISO. Known relevant files from camd11's changelog:
   - `SLPS_258.36` (boot ELF): UI string table, menu code, banner renderers, backlog code
   - `/OL/MPOL.BIN`, `/OL/W1OL.BIN` and other `/OL/*.BIN`: code overlays with their own
     string tables (Spirit menu, map/intermission UI)
   - `/DATA/MAP.BIN`: stage blocks with objective text (179 conditions in 41 blocks) and the
     terrain name table (148 names), pointer tables
   - `GRAPHIC.BIN`: fonts, UI sprites, banners
   - Story script: most likely in a per-stage event/scenario archive; find it by searching
     Shift-JIS for a known line from stage 1
2. Catalogue every container: magic, entry count, offset/size tables, compression (check for
   LZSS/LZ77 variants typical of Banpresto PS2 titles; many files are uncompressed).
3. Map the text systems. Expect at least four, each needing its own tool:
   - Story/VN dialogue (speaker + body, control codes for wait/newline/color/name)
   - Battle quotes (per pilot, per situation)
   - Fixed UI strings in ELF and overlays (pointer tables, in-place limits)
   - Baked-in art (title logo, chapter cards, sortie banners, button hint sprite font)
4. Font: identify the glyph bitmap, cell size, encoding (Shift-JIS to cell index), and
   whether a width table exists. camd11 replaced the fixed-width JP cell font with a
   proportional English font and had to hook the width logic. Plan for that from the start.
5. Write it all down in `docs/formats.md` as you go. This document is the project.

## 4. Build the toolchain (weeks 2 to 4)

Write these in Python, in `tools/`, each with a round-trip test (extract, reinsert unchanged,
diff must be byte-identical before you translate anything).

- `iso_tool.py`: list, extract, and in-place write files by LBA into the ISO.
- `archive_tool.py`: unpack/repack each container type found in step 3.
- `script_dump.py` / `script_insert.py`: story text to and from a line-based format
  (ID, speaker, JP, EN, control codes preserved). Output something diff-friendly such as
  TSV or one JSON per stage.
- `strtab_tool.py`: pointer-table string editor for ELF and overlay string tables. Must
  support relocating strings to free space and rewriting pointers, not just in-place edits.
  camd11's Spirit-menu crash came from in-place edits corrupting pointer entries, and their
  0.2.8 hardware bug came from relocating data into ELF space that the CD/controller
  drivers actually use. Validate free space by running on hardware, not just PCSX2.
- `font_tool.py`: dump the glyph atlas to PNG, import an edited atlas, generate a width table.
- `tex_tool.py`: dump and reimport the UI textures (TIM2 or raw swizzled 4/8-bpp with CLUT).
- `build.py`: one command from `translation/` + clean ISO to patched ISO + xdelta + checksums.

## 5. Make English render before translating anything (week 4 to 5)

This is the hacking milestone that gates everything else.

1. Get ASCII (1-byte) characters drawing in the dialogue box. The renderer reads strictly
   two bytes per glyph; patch it to accept 1-byte codes (camd11 patched both VN banner
   drawers in the ELF for exactly this).
2. Install a proportional font plus width table and hook the advance/centering code.
3. Fix line-wrap and box-size limits so English (about 1.5x to 2x JP width) fits.
4. Repeat for menus, battle banners, backlog, save slot titles.
5. Test on PCSX2 and on a real PS2 via OPL at every ELF change. The emulator hides
   memory-corruption bugs that hardware exposes.

## 6. Translation (weeks 5 to 12, overlaps with hacking)

- Dump the full script. Expect on the order of 20,000 dialogue lines
  (camd11 re-wrapped about 19,500) plus a few thousand UI and battle strings.
- Build a glossary first: pilot and unit names, attack names, Spirit commands, terrain ranks.
  Use Kingcom's OG: Original Generations patch as the canonical reference for shared terms
  so this game matches its prequel.
- AI first pass: feed the script stage by stage with the glossary, speaker, and the
  preceding lines as context. Have the model preserve control codes and respect a max
  pixel width per line (compute from your width table and reject lines that overflow).
- Human pass: you read every line in context. AI output is fine for a draft, not for
  character voice, honorifics, and jokes. This is the most time-consuming step and the
  one that decides whether the patch is good or merely playable.
- Keep JP and EN side by side in the repo so reviewers can file corrections as PRs.

## 7. Art (parallel track)

Title logo, chapter/episode cards, sortie banners, Shuffle Battler banners, card-mode menu,
button-hint sprite font (the one camd11 never fixed), terrain and Spirit icons. Dump to PNG,
redraw with matching palette constraints, reimport. Do the sprite font properly: add Latin
glyph cells so the footer hints are text instead of garbled pixels.

## 8. Integration, QA, release

1. Full playthrough on PCSX2, then on hardware. Log every overflow, crash, and mistranslation
   with a save state and stage ID.
2. Regression suite: a script that reinserts the current translation and checks that every
   string fits its width budget and every pointer table still validates.
3. Release: xdelta, checksums, README (what is translated, known issues), CHANGELOG.
   Post to romhacking.net, r/SuperRobotWars, GBAtemp.
4. Expect several point releases. camd11 went from 0.2 to 0.2.9 fixing crashes, banners,
   and hardware freezes.

## 9. How this session can help

- Writing and testing every tool in `tools/` once you give me a handful of extracted files
  (the ELF, the overlays, MAP.BIN, a story archive, GRAPHIC.BIN). Do not push them to
  GitHub; upload them to the session or keep them local and run my scripts there.
- Ghidra-style analysis of the text renderer and pointer tables from a disassembly dump.
- The AI first-pass translation with glossary enforcement and width checks.
- Building the font atlas and width table.

## Sources

- https://github.com/camd11/srw-og-gaiden-en (README, CHANGELOG)
- https://www.romhacking.net/translations/5513/
- https://www.romhacking.net/forum/index.php?topic=41450.0
- https://www.romhacking.net/forum/index.php?topic=24453.0 (cancelled OGs project, same engine lineage)
- https://akurasu.net/wiki/Super_Robot_Wars/OGs/English_Patch
