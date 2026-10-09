# File formats (2nd Super Robot Wars OG, BLJS10133)

Everything below was confirmed on our own dump with byte-identical round trips
(`tools/*.py roundtrip`). All integers are big-endian unless stated. All text is
UTF-8 (not Shift-JIS), NUL-terminated, full-width punctuation and digits.

Per-container details that live in their own files:

- FIXH data tables (`Logic/Dat/FixedData/*.dat`): `formats-fixh.md`
- BMD battle messages (`Battle/Dat/Battle/Message/*.bmd`): `formats-bmd.md`
- CSB (Q&A, archive, staff roll) and WTD (window tool data): `formats-csb-wtd.md`

## Disc layout

```
PS3_GAME/USRDIR/EBOOT.BIN                 encrypted SELF; EBOOT.elf = decrypted (rpcs3 --decrypt)
PS3_GAME/USRDIR/PSARC/Logic.psarc.sdat    scripts, data tables, menus for the area map
PS3_GAME/USRDIR/PSARC/Common.psarc.sdat   fonts, Q&A, archive, titles, save data UI
PS3_GAME/USRDIR/PSARC/General2d.psarc.sdat window data (all menus), faces, intermission backgrounds
PS3_GAME/USRDIR/PSARC/General3d.psarc.sdat map models, particles, unit tool data
PS3_GAME/USRDIR/PSARC/Battle.psarc.sdat   battle animations and battle messages
PS3_GAME/USRDIR/PSARC/Movie.psarc         plain psarc, no text
PS3_GAME/USRDIR/PSARC/Sound.psarc         plain psarc, no text
PS3_GAME/USRDIR/PSARC/PsarcList.bin       180 bytes, list of the above
```

## SDAT wrapper (`tools/sdat.py`)

Licence-free NPDRM EDATA. NPD header 0x80 bytes, EDAT header 0x10, then
per-block metadata + ciphertext.

| offset | size | field |
|---|---|---|
| 0x00 | 4 | `NPD\0` |
| 0x04 | 4 | version = 4 |
| 0x08 | 4 | license = 0 |
| 0x0C | 4 | type = 0 |
| 0x10 | 0x30 | content id (all zero) |
| 0x40 | 0x10 | digest (used as the AES-CBC IV) |
| 0x50 | 0x10 | title hash |
| 0x60 | 0x10 | dev hash (XORed with SDAT_KEY to make the file key) |
| 0x80 | 4 | flags = 0x0100003C |
| 0x84 | 4 | block size = 0x4000 |
| 0x88 | 8 | payload size |
| 0x90 | 0x10 | AES-CMAC of the concatenated block metadata |
| 0xA0 | 0x10 | AES-CMAC of bytes 0x00..0xA0 |
| 0xB0 | 0x28 | ECDSA signature (metadata) |
| 0xD8 | 0x28 | ECDSA signature (header) |
| 0x100 | | blocks |

Flags: SDAT (0x01000000), metadata precedes each block (0x20), HMAC key is
double-encrypted (0x10), key is encrypted with EDAT_KEY_1 (0x08). Not
compressed. Each block = 0x20 metadata + ciphertext (block size, last block
rounded up to 16). Metadata bytes 0..16 are the SHA1-HMAC XORed with bytes
16..32; bytes 16..20 are HMAC bytes 16..20; bytes 20..32 are a random mask.

Key schedule per block i (see the docstring in `sdat.py` for the exact
sequence). The HMAC is over the ciphertext. The header and metadata CMACs use
AES-CBC-decrypt(EDAT_KEY_1, 0)(file key) as the CMAC key. RPCS3 checks the
per-block HMACs only; we recompute all three anyway. The ECDSA signatures
cannot be regenerated and are copied from the original; RPCS3 ignores them.

Example: `Logic.psarc.sdat` has 1614 blocks, payload 26,442,860 bytes, 16
trailing bytes after the last block.

## PSARC v1.4 (`tools/psarc.py`)

```
0x00 "PSAR" u16 1 u16 4 "zlib"
0x0C u32 toc_length (= offset of first data byte)
0x10 u32 toc_entry_size = 30
0x14 u32 toc_entries (manifest counts as entry 0)
0x18 u32 block_size = 0x10000
0x1C u32 archive_flags = 2 (absolute paths)
0x20 TOC entries: md5(name)[16] u32 first_block u40 size u40 offset
     block table: u16 per block (stored length, 0 = full raw block)
     data
```

Entry 0 is the manifest (newline-separated names, md5 all zero). Each 64 KB
block is an independent zlib stream at level 9 (default window/memory/strategy)
or stored raw when zlib would not shrink it. Identical files share one block
run (56 of 824 entries in Logic). All five archives recompress identically
with Python's zlib (Battle: 120,810 blocks, 0 mismatches).

## Text carriers

| carrier | files | strings | tool |
|---|---|---|---|
| LDBI talk scripts | `Logic/Dat/logic/talk/ls000..101, 990, 991, 999.bin` (102) | ~50,000 incl. labels | `script.py` |
| LOGO stage scripts | `Logic/Dat/logic/scr*.bin` (102) | ~13,000 incl. labels | `script.py` |
| FIXH data tables | `Logic/Dat/FixedData/*.dat` (26) | names, help, dictionaries, trophies | `fixh.py` |
| BMD battle messages | `Battle/Dat/Battle/Message/*.bmd` (127) | battle quotes | `battle.py` |
| WTD window data | `General2d/.../windowdataMain.wtd`, `Logic/.../areamapwindow.wtd` | all menu text | `wtd.py` |
| CSB | `Common/Dat/Option/QA/2og_Q&A.csb`, `Common/Dat/Archive/Csb/*.csb`, staff roll, summary | Q&A, story recaps | `csb.py` |
| EBOOT | `EBOOT.elf` data segment 0xC2F000..0xC78000 (+ scattered) | ~2,300 incl. debug | `eboot_strings.py` |

Not text: `Battle/Dat/Battle/Anime/Csv/*U8.csv` are developer spreadsheets of
animation sequences (names only as comments); `General3d/.../UnitToolData/*.utd`
contain only the word プレイヤー. Fonts: `Common/Dat/Font/font.bin`,
`exFont01..05.bin`.

## LDBI talk script (`tools/script.py`)

```
0x00 "LDBI"      0x04 u32 1000
0x08 u32 0       0x0C u32 string_count (string 0 is "")
0x10 u32 1       0x14 u32 offset of string offset table
0x18 u32 0x30    0x1C u32 offset of section 2 (always 0x1A80 bytes)
0x20 u32 n3      0x24 u32 offset of section 3 (4 + n3 * 132 bytes)
0x28 u32 n4      0x2C u32 offset of section 4 (4 + n4 * 12 bytes)
0x30..0x80       little-endian editor metadata, kept verbatim
0x80             string pool
```

The pool holds string_count NUL-terminated strings; the offset table holds
string_count u32 absolute file offsets. Pool and table are zero-padded to
128 bytes and always receive padding (a full 128-byte block when already
aligned, seen in ls049/ls059/ls092). Sections 2..4 are copied verbatim.

Section 3 records (132 bytes = 33 u32) are the dialogue commands. Words 1..3
are string indices: speaker label (`[ＤＭ]-アイビス` style), then text. Section
4 (12 bytes: type, 2n, string index) lists the cast of the scene. Nothing
references the pool by file offset, so strings may change length freely.

Strings: first ~80 are `[ＤＭ]-name` speaker labels and `[１]-001` style event
keys (keep as-is), then dialogue. `@` is the in-message line break, usually
followed by an ideographic space. Example from ls000:

```
#120 「くっ！　ここまでとはな…！」
#245 （……左肩部バーニア・スラスター、破損。@　左足首のダンパー・スタビライザーもぎこちない）
#240 Dat/Sound/Me/me002.msf          <- asset path, keep as-is
```

## LOGO stage script (`tools/script.py`)

```
0x00 "LOGO"  0x04 u32 file_size  0x08 u32 0  0x0C u32 0
0x10.. ten (count, offset) pairs. Bytecode sections at 0xC0, 0x140, 0x540,
       0x2DC0, 0x61C0 (DEADDEAD-padded), then:
0x40 (nA, tableA)   0x48 (nA, poolA)   0x50 (nB+1, tableB)   0x58 (nB, poolB)
0x6C u32 file_size again
```

tableA: nA u32 offsets relative to poolA. tableB: nB+1 offsets relative to
poolA, last = end of strings. tableA/tableB are contiguous and the table
region is padded to 64 bytes; poolA/poolB are contiguous and padded to 64
bytes. Fill: 0xAD up to the next 4-byte boundary, then little-endian
0xDEADDEAD words (bytes AD DE AD DE). In 5 of 102 files the loose bytes before
the boundary are uninitialised garbage, so the builder keeps the original fill
when the layout is unchanged.

Pool A (78 strings in every file): `[ＤＭ]-name` unit/speaker labels. Pool B:
talk file name (`ls000.bin`), event keys (`[ＳＤ１]-000`, `[１]-000`), victory
and defeat conditions, stage title. Width tag seen: `<W=63>　</W>`.

## Build and deploy

`work/` layout (outside OneDrive, `C:\Users\antho\srw2og-work`):

```
pristine/USRDIR/...      untouched game files + SHA256SUMS.txt
dec/<name>.psarc         decrypted archives
ext/<name>/              extracted archives
```

Build: worksheets -> patched files in a copy of `ext/Logic` -> `psarc.py pack`
with the original as template -> `sdat.py encrypt` with the original as
template -> copy over `dev_hdd0/disc/BLJS10133/PS3_GAME/USRDIR/PSARC/`.
