# 2nd Super Robot Wars OG (PS3, BLJS10133) English Translation: Course of Action

## 0. What already exists (read this first)

Two things cover most of the ground, and both are public.

**A. A full machine-translated patch with open tools.**
`srwogs2ndeng/og2-translation` on GitHub (v1.0.22, 2026-09-13; first release 2026-09-04).
- About 87,000 strings: story script, battle quotes, menus, library, help, skills, parts, map names.
- About 50 Python scripts (PSARC extract/pack, SDAT decrypt/encrypt, FIXH/WTD/BMD/script tools,
  30 EBOOT code patches for Latin glyph spacing and auto-fit, fSELF builder, deploy with rollback).
- Translations stored as JSON worksheets keyed by Japanese file offset; builds are reproducible
  from a pristine extract; no game data in the repo.
- `docs/HACKING.md` documents the containers and text formats. `PROCESS.md` documents the
  AI workflow and QA gates.
- Weak point, stated by its own author: the 41,473 dialogue lines were LLM-translated in
  ~180-line chunks and only spot-checked. Expect stiff dialogue, wrong pronouns, flattened jokes.
- Tested on RPCS3 only (Windows end to end; Linux and Steam Deck boot). Never run on a real PS3.
- No license file. Default copyright applies, so forking or reusing code needs the author's OK.
  The repo is anonymous (one commit, "anon snapshot" tooling) but has an issue tracker.

**B. A full human story translation.**
Ian "NrvnqsrKhaos" Maatta, https://2ndsrwoge.com/. All story dialogue plus narration across
roughly 90 chapter pages covering every route (Lune/Masaki, Earth/Space branches, both endings).
Informal register with strong language by the translator's own description. Contact:
2ndSRWOGTranslation@gmail.com.

**What is actually missing**, and therefore the project worth doing:
1. A human-quality script inside the game. Nobody has combined A's insertion pipeline with
   a properly edited English script.
2. Real-hardware support and testing (PS3 with HEN/CFW).
3. A licensed, documented toolchain others can build on.

## 1. Decision: build on the open toolchain, spend your effort on the script

Do not re-derive the file formats from scratch. That work is done and documented. Your
"cut my teeth" value comes from (a) running and understanding every step of the pipeline on
your own dump, (b) fixing what the MTL project left broken, and (c) producing the script.

Before writing code, open an issue on og2-translation asking the author to add a license
(MIT or GPLv3) and whether they welcome a script-quality fork. If no answer within a couple of
weeks, reimplement the tools yourself using HACKING.md as the spec. The format knowledge is
not copyrightable; the code is.

Also email NrvnqsrKhaos asking permission to use the 2ndsrwoge.com translation as a reference
for an in-game script, with credit. Their text is a meaning reference, not drop-in dialogue:
the register and profanity would need editing to match the game's tone anyway.

## 2. Legal and repo hygiene

- Dump BLJS10133 from a disc you own. The retail disc, not the Premium Edition, unless you
  verify that both share the same USRDIR contents.
- Never commit game data. `.gitignore` covers `*.psarc`, `*.sdat`, `EBOOT*`, `*.self`,
  `*.elf`, `work/`, `build/`. The repo holds tools, JSON worksheets (JP + EN), glossary,
  docs, and release scripts. The user rebuilds from their own dump, exactly as og2 does.
- Rename this GitHub repo; it is still named for OG Gaiden.

## 3. Workstation

| Need | Tool |
|---|---|
| Emulator | RPCS3 (latest). For renderer work, a custom build with `HAS_MEMORY_BREAKPOINTS` as og2 did |
| Disassembly | Ghidra with the PS3/Cell PPC64 loader for the decrypted EBOOT; capstone for scripted analysis |
| Decryption | RPCS3 Utilities > Decrypt PS3 Binaries for EBOOT; `decrypt_sdat.py` lineage (make_npdata, GPLv3) for SDAT |
| Hex | ImHex or 010 Editor |
| Textures | DDS (og2 has `dds_tool.py`); GIMP or Photoshop with DDS plugin for redraws |
| Python | 3.10+, `cryptography`, `capstone`, `Pillow` |
| Hardware | A PS3 on HEN or CFW, with webMAN, for the hardware track (section 7) |

## 4. Pipeline bring-up (weeks 1 to 2)

Goal: a no-op round trip that is byte-identical, on your dump, with tools you understand.

1. Decrypt the five SDAT-wrapped PSARCs (Logic, Battle, Common, General2d, General3d).
   Confirm every SDAT block HMAC validates after re-encryption; RPCS3 treats a bad block as fatal.
2. Extract and inventory. Known text carriers:
   - `Logic/Dat/logic/talk/ls*.bin`: story script (growable)
   - `Logic/Dat/FixedData/*.dat`: FIXH containers (SOFS 32-bit BE offsets, STRI block;
     some files are position-addressed and must keep exact byte lengths)
   - BMD: battle quotes
   - `General2d/.../windowdataMain.wtd`: menu UI, per-record font size floats
   - MTI: 1024 fixed 84-byte terrain records
   - CSB: Q&A screens
   - EBOOT string table: ~2,000 system strings, no length growth allowed
3. Re-pack unchanged, re-encrypt, deploy to RPCS3, boot. Then diff: must be byte-identical.
4. Write `docs/formats.md` in your own words as you verify each format. Treat HACKING.md as
   a claim to check, not gospel; the 16-bit-offset misread they shipped for a while shows why.

## 5. Script dump and alignment (weeks 2 to 4)

1. Dump every `ls*.bin` to a worksheet: file, offset, speaker ID, JP text, control codes,
   byte budget. Resolve speaker IDs to names. Keep the bracketed `[...]-` engine keys and
   anything else the engine byte-matches untouched (og2 found ~10,300 of these).
2. Map script files to the game's stage/route structure so a translator works in story
   order with route context.
3. Pull og2's existing English worksheets (if licensed) as a third column: a machine draft
   to edit against rather than a blank page. If not licensed, generate your own draft (step 6).
4. Build a glossary before translating a line. Sources, in priority order:
   - Official English names from OG: The Moon Dwellers (PS4 Asia English) and OG1/OG2 (GBA, Atlus)
   - Kingcom's OGs patch for anything only in the PS2 games
   - Consistent romanizations for 2nd OG-only terms (Four Gods, Boundary Realm, etc.)
   Store it as data the tools enforce, not a wiki page.

## 6. Translation (weeks 4 to 16, the bulk of the project)

- 41,473 dialogue lines plus ~34,000 battle lines (mostly short, highly repetitive after dedup).
- AI first pass, done properly: feed one scene at a time with the glossary, speaker names,
  the previous scene, the matching 2ndsrwoge.com chapter as a meaning reference, and the
  pixel/byte budget. Require JSON output, reject anything that drops a control code or
  overflows, fall back to Japanese rather than ship a broken line.
- Human edit pass, every line, in context, in the game or in a script viewer with speaker
  portraits. This is the deliverable that separates this project from the MTL. Budget it
  honestly: 41k lines at a few hundred edited lines per hour is well over 100 hours.
- Style guide: honorifics policy, how each pilot talks, attack-name capitalisation,
  battle-bark tone. Write it before the edit pass, not after.
- Keep JP and EN side by side in git so reviewers can send corrections as pull requests.

## 7. Rendering and hardware (parallel track, weeks 2 onward)

- The RPCS3 rendering problem is solved: 30 EBOOT patches (glyph advance K=0.57, font-size
  floor, auto-fit comparison fixed to measure at K, justify path redirect) in a code cave at
  `0xc45928`. Reproduce them on your dump and read every one until you understand it.
- Known leftovers to fix: opening crawl centering (currently ragged), ASCII `<>` parsed as
  control tags in command menu labels, weapon name width limit below 25 chars, route cards
  overflow.
- Hardware: og2 ships a fake-signed SELF, which runs on HEN/CFW but not OFW. Test on a real
  PS3 early. The OG Gaiden PS2 project found a memory-corruption bug that the emulator hid and
  hardware exposed; expect the same class of bug here, especially around the code cave and
  stack red-zone use (og2 crashed once on exactly that).
- Art: title logo and any baked-in English-needed textures live in DDS inside General2d.
  og2's override repack appends the changed file and repoints the TOC instead of rebuilding
  the 638 MB archive; keep that technique.

## 8. QA gates (automated, run on every build)

- No-op rebuild is byte-identical.
- Every SDAT block HMAC validates.
- EBOOT strings: format specifiers and `@`/`\n` markers preserved, no length increase.
- Position-addressed FIXH files: every segment keeps its original byte length.
- Every dialogue line fits its measured width at the patched font metrics.
- Glossary check: no non-canonical name in any English string.
- Then a full playthrough of every route on RPCS3, and at least the main route on hardware.

## 9. Release

- Installer that rebuilds from the user's own dump (no game data distributed), with
  pre-deploy backups and rollback, like og2's `apply.py`.
- README with what is translated, what is intentionally Japanese, tested platforms, known issues.
- CHANGELOG. Post to r/SuperRobotWars, RetroGameTalk fan translations, GBAtemp, romhacking.net.
- Credit og2-translation for the toolchain research and NrvnqsrKhaos for the reference
  translation, per whatever terms they give you.

## 10. How this session can help

- Reimplement or review any of the tools once you can give me extracted, decrypted files
  (a few FIXH files, two or three `ls*.bin`, the WTD, the decrypted EBOOT). Do not push them
  to GitHub; upload to the session or run my scripts locally.
- Build the glossary from official English sources and the enforcement tooling.
- Run the AI first pass with scene context, glossary, and budget checks.
- Write the regression gates in section 8.
- Draft the license and permission requests to the two existing authors.

## Sources

- https://github.com/srwogs2ndeng/og2-translation (README, docs/HACKING.md, PROCESS.md, CHANGELOG.md)
- https://2ndsrwoge.com/ and https://akurasu.net/wiki/Super_Robot_Wars/OG2nd/Story_Translation
- https://github.com/nutsamasan/srw-ogmd-tools (Moon Dwellers PS3 tools, GPLv3, same era and publisher)
- https://github.com/camd11/srw-og-gaiden-en (OG Gaiden PS2; hardware-vs-emulator lessons)
