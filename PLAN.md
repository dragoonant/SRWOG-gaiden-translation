# 2nd Super Robot Wars OG (PS3, BLJS10133) English Translation: Plan

## Decisions (locked)

- **Independent project.** Our own tools, our own translation from the Japanese. We do not fork,
  reuse, or ask permission from the existing MTL patch (srwogs2ndeng/og2-translation) or the
  read-along site (2ndsrwoge.com). Their public write-ups are useful as a list of pitfalls to
  verify against, nothing more. Every format is confirmed on our own dump.
- **Terminology canon:** the fan patches of *OG: Original Generations* (PS2, Kingcom) and
  *OG Gaiden* (PS2, camd11). Those two games precede 2nd OG directly and their naming is what
  players already know. Not used: *Moon Dwellers* (official but poorly edited, chronologically
  later) and the GBA OG1/OG2 names where they differ from the PS2 patches.
- **Translation workflow:** full AI pass over every string first, then Anthony edits line by line.
- **Target platform:** RPCS3 only. No real-hardware track (the PS3 on hand is not jailbroken).
- **Division of labour:** Anthony supplies the game data, the decrypted EBOOT, playtesting, and
  the edit pass. Claude does everything else: reverse engineering, tools, extraction, glossary,
  AI translation, reinsertion, builds, regression checks, release packaging.

## What already exists (for awareness, not reuse)

- srwogs2ndeng/og2-translation: machine-translated patch, ~87,000 strings, RPCS3 only,
  released 2026-09-04, now v1.0.22. Dialogue was LLM-translated and spot-checked only.
- 2ndsrwoge.com by NrvnqsrKhaos: human read-along translation of the full story, by route and
  chapter. Not a patch.
- Our differentiator when we release: every line human-edited, names consistent with the PS2
  OGs and OG Gaiden patches.

## What Anthony does (the complete list)

1. **Supply the game data once.** Either the full ISO or a zip of `PS3_GAME/USRDIR` from your
   BLJS10133 dump, via a direct-download link (a Google Drive "anyone with the link" share is
   fine). If the ISO came from a PC Blu-ray drive it is encrypted and needs the 32-hex-character
   disc key (`.dkey`); include it. Never put game data in the GitHub repo.
2. **Decrypt the EBOOT once.** In RPCS3: install firmware, add the game, confirm it boots in
   Japanese. Then Utilities > Decrypt PS3 Binaries on `PS3_GAME/USRDIR/EBOOT.BIN`. Upload the
   resulting `EBOOT.ELF` the same way as step 1. Claude cannot do this: it needs the firmware
   keys that only your RPCS3 install has.
3. **Sign off the names list** before the AI pass starts (section 4). One review of a short table.
4. **Playtest each build in RPCS3.** Copy the build's output over your RPCS3 game folder as the
   build script instructs, play, and report bugs with a screenshot and roughly where you were.
   Claude fixes and rebuilds.
5. **Edit pass.** Edit the English column of the worksheet files in the repo (plain text or
   spreadsheet export, your choice). Commit or send them back. Claude rebuilds, re-runs the
   fit checks, and flags anything that no longer fits.
6. **Rename the repo** on github.com to `srw-2nd-og-translation` (Claude's proxy cannot change
   repo settings).

Optional: an Anthropic API key as an environment secret lets the AI pass run as a batch job
instead of inside interactive sessions. Faster and cheaper for 87,000 strings; not required.

## What Claude does

### Phase 1: pipeline bring-up (first session after data arrives)

1. Decrypt the ISO if needed, extract `PS3_GAME/USRDIR`, inventory every file with sizes and magics.
2. Decrypt the five SDAT-wrapped PSARC archives (Logic, Battle, Common, General2d, General3d).
   SDAT without a licence uses a fixed key scheme; implement decrypt and encrypt in Python and
   verify every per-block HMAC on re-encryption. RPCS3 treats a bad block as fatal.
3. Extract each PSARC. Repack unchanged. Diff must be byte-identical before any edit.
4. Catalogue every text carrier by reading the bytes, not by trusting anyone's docs. Expected:
   story scripts under `Logic/Dat/logic/talk/`, FIXH containers under `Logic/Dat/FixedData/`
   (unit, pilot, weapon, skill, parts, help, spirit, ACE bonus data), battle-quote files,
   the menu window data in General2d, terrain name records, Q&A screens, and the EBOOT
   string table. Document each in `docs/formats.md` with offsets and worked examples.
5. Write the tools in `tools/`, each with a round-trip test:
   `sdat.py`, `psarc.py`, `fixh.py`, `script.py`, `battle.py`, `wtd.py`, `eboot_strings.py`,
   `worksheet.py` (JSON per game file keyed by offset: JP, EN, budget, control codes),
   `build.py` (pristine extract + worksheets -> patched archives + fSELF), `deploy.py`
   (copy into an RPCS3 game folder with backup and rollback).

### Phase 2: rendering (needs the decrypted EBOOT)

1. Disassemble the EBOOT (Ghidra headless, PPC64, plus capstone scripts). Locate the text
   measure, draw, auto-fit and justify routines and the font-size setter.
2. Expected problems, to confirm on our binary: Latin glyphs advanced with Japanese metrics
   (too wide), auto-fit shrinking long English lines to unreadable sizes, measurement and
   drawing using different scale factors, ASCII `<>` parsed as control tags.
3. Write the code patches into an unused run of zeroes in the EBOOT, with a patch script that
   asserts the target bytes before writing. Rebuild as an fSELF for RPCS3.
4. Anthony playtests a Japanese build with only the renderer patches applied, to separate
   rendering bugs from text bugs.

### Phase 3: glossary

1. Build the names table from the PS2 patches. Two sources, cross-checked:
   - Dump the English pilot, unit, weapon, Spirit, skill and terrain tables from patched OGs and
     OG Gaiden ISOs (Anthony applies the patches to his own PS2 dumps; Claude writes the dumper).
   - The Akurasu wiki pages documenting those patches, as a secondary check.
2. For 2nd OG-only characters, units and attacks (the Masou Kishin cast beyond what Gaiden had,
   the MX and Alpha 3 guests, the new antagonists), propose a romanization table and get
   Anthony's sign-off.
3. Store the glossary as data (`glossary/*.tsv`) that the fit-check step enforces: a build fails
   if any English string uses a non-canonical form of a glossary term.
4. Write the style guide: honorifics policy, speech patterns per pilot, attack-name casing,
   battle-bark register, punctuation rules (half-width ASCII, no `;` where the engine treats it
   as a line break, which brackets are control tags).

### Phase 4: AI translation pass

- Story: one scene at a time, in route order, with speaker names, the previous scene, the
  glossary, the style guide, and each line's byte or pixel budget. Output is structured and
  validated: control codes preserved, budget respected, glossary respected. Anything that fails
  falls back to the Japanese and is logged for the edit pass.
- Battle quotes: deduplicated first (tens of thousands of lines, heavily repeated), translated
  with pilot context, genders left unspecified where the Japanese leaves them unspecified.
- Menus, library, help, skills, parts, EBOOT strings: translated against hard byte limits,
  shortened by rule where needed, and the shortening decisions listed for Anthony.
- Bracketed engine keys and anything the engine byte-matches stay Japanese on purpose.
- Deliverable: a complete English build Anthony can play end to end, plus the worksheets.

### Phase 5: edit pass support

- Worksheets exported in whatever form Anthony prefers (TSV, spreadsheet, or a small local web
  viewer with speaker portraits if useful).
- Every re-import is rebuilt and re-checked; lines that now overflow are listed with the
  budget they exceed.

### Phase 6: QA gates and release

- Gates on every build: byte-identical no-op rebuild, every SDAT HMAC valid, format specifiers
  and control markers preserved, fixed-length records unchanged in length, every line within
  budget, glossary clean.
- Anthony plays every route (Lune and Masaki routes, Earth and Space branches, both endings).
- Release: an installer that rebuilds from the user's own dump (no game data distributed),
  README (coverage, intentionally Japanese strings, known issues), CHANGELOG, posts to
  r/SuperRobotWars, RetroGameTalk, GBAtemp.

## Repo layout

```
tools/        Python tools (MIT licence)
docs/         formats.md, style-guide.md, install.md
glossary/     names, attacks, spirits, terrain (TSV)
worksheets/   one JSON per game file: JP, EN, budget, flags
build/        output, gitignored
work/         pristine extracts, gitignored
```

## Session logistics

The cloud container is ephemeral. Tools, worksheets, glossary and docs live in git and are
pushed after every session. Game data is re-downloaded from Anthony's link when a fresh
container starts; the build is reproducible from the pristine extract, so nothing is lost.
