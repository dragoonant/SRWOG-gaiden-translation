# CSB table files and WTD window files

Game: 2nd Super Robot Wars OG, PS3, BLJS10133. Both formats are big-endian with UTF-8 text.
Tools: `tools/csb.py` and `tools/wtd.py` (`info`, `dump`, `extract`, `build`, `roundtrip`,
`selftest`; `wtd.py` also has `audit`).

Status: `csb.py roundtrip` rebuilds all 12 CSB files and `wtd.py roundtrip` both WTD files
byte-for-byte from their worksheets. **Confirmed** means checked programmatically on every
file by those commands. **Inferred** means a reading of the data that nothing in the tools
depends on, or that has not been tried in the game.

---

## 1. CSB (`CSB `) - string-table spreadsheets

Files (12, all under `ext/`): `Common/Dat/Archive/Csb/Archive_{Ending,OG1,OG2,OGg}.csb`,
`Common/Dat/Option/QA/2og_Q&A.csb`, `Common/Dat/Option/ScenarioChart/ScenarioChart.csb`,
`Logic/Dat/Roll/Csb/{Roll_01_cnv,Telop_001,Telop_002,Telop_002_Work2,Telop_003}.csb`,
`Logic/Dat/logic/Resource/summary/2og_GuidanceSummary.csb`. No other `*.csb` exists in
Common, General2d or Logic.

A CSB is a table: a pool of NUL-terminated strings plus rows of cells; every cell is a
reference to a pool string. Numbers are strings too (`"60"`, `"-1"`).

### 1.1 Layout (confirmed)

```
offset  size  content
0x00    4     "CSB "
0x04    4     FE FF 01 00   (constant; looks like BOM + version 1.0)
0x08    4     FF FF 00 00   (constant)
0x0C    4     u32 total number of cells in all rows
0x10    1     u8  number of cells in the widest row (then 00 00 00)
0x14    4     u32 row count
0x18          chunk STRP
              chunk LNP
              chunk LNT                         <- file ends here
```

The three header words at 0x0C/0x10/0x14 are redundant with the chunks (checked in every
file); they never change when text is edited, so build copies the 0x18 header verbatim.

Every chunk is `tag(4) size(4) count(4) payload`, `size` counts the whole chunk including
the 12 header bytes, and every chunk starts 4-byte aligned.

| chunk | payload |
|---|---|
| `STRP` | `count` NUL-terminated UTF-8 strings back to back, then 0..3 padding bytes to a 4-byte boundary. Strings are unique and every one is referenced. Pool string 0 is not special. |
| `LNP ` | `count` rows. Row = `u32 n`, `u32 ptr`, `n * u32 cell`. `ptr` is the absolute file offset of the first cell, always the word right after the pair (row start + 8). A cell is the **absolute file offset** of a STRP string. A row with `n = 0` is just the pair (empty row). |
| `LNT ` | `count` (= row count) `u32` absolute file offsets of each row's `n` word. `size` is always `12 + 4 * count`. |

What depends on string length (confirmed): the STRP `size`, the 4-byte padding, every cell
offset, every row `ptr`, the LNP `size`, every LNT entry. `build` regenerates all of them
from (strings, row structure); nothing else in the file changes.

Padding: 0..3 bytes after the pool. In 4 of 12 files it is not zero but leftover bytes of
the last string (`Telop_002` has `2c`, its sibling `Telop_002_Work2` has `31`, OG2 `6473`,
OGg `81a8`). Build reuses the original pad bytes when the pool is unchanged and writes
zeros once any string changed.

### 1.2 Worked example: `Archive_Ending.csb` (192 bytes, whole file)

```
0000  43 53 42 20 fe ff 01 00 ff ff 00 00   "CSB " + constants
000C  00 00 00 0a        10 cells in total
0010  05 00 00 00        widest row has 5 cells
0014  00 00 00 04        4 rows
0018  53 54 52 50        "STRP"
001C  00 00 00 38        chunk size 0x38 -> next chunk at 0x50
0020  00 00 00 09        9 strings
0024  36 30 00           "60"            @0x24
0027  30 00              "0"             @0x27
0029  36 31 00           "61"            @0x29
002C  31 00              "1"             @0x2C
002E  32 00              "2"             @0x2E
0030  31 30 30 00        "100"           @0x30
0034  6d 5f 73 72 5f 30 30 2e 70 61 6d 00   "m_sr_00.pam"  @0x34
0040  44 61 74 2f 4d 6f 76 69 65 2f 00      "Dat/Movie/"   @0x40
004B  31 31 00           "11"            @0x4B
004E  00 00              pad to 4 (garbage-capable)
0050  4c 4e 50 20  00 00 00 54  00 00 00 04      "LNP ", size 0x54, 4 rows
005C  00 00 00 02 00 00 00 64   row 0: n=2, ptr=0x64
0064  00 00 00 24 00 00 00 27   cells -> "60", "0"
006C  00 00 00 02 00 00 00 74   row 1: n=2, ptr=0x74
0074  00 00 00 29 00 00 00 2c   cells -> "61", "1"
007C  00 00 00 05 00 00 00 84   row 2: n=5, ptr=0x84
0084  00 00 00 2e 00 00 00 30 00 00 00 27 00 00 00 34 00 00 00 40   "2","100","0","m_sr_00.pam","Dat/Movie/"
0098  00 00 00 01 00 00 00 a0   row 3: n=1, ptr=0xA0
00A0  00 00 00 4b               cell -> "11"
00A4  4c 4e 54 20  00 00 00 1c  00 00 00 04   "LNT ", size 0x1C, 4 rows
00B0  00 00 00 5c 00 00 00 6c 00 00 00 7c 00 00 00 98   row offsets
00C0  EOF
```

If `m_sr_00.pam` is replaced by `m_sr_00_alt.pam` (+4 bytes): STRP size becomes `0x3C`, the
three later strings move +4, so the cells for `Dat/Movie/` and `11` become `0x44`/`0x4F`,
LNP moves to 0x54 and every row `ptr` (`0x64` -> `0x68`, ...), every LNT entry (`0x5C` ->
`0x60`, ...) shift by 4. That is exactly what `csb.py build` produced; the file is 196 bytes.

### 1.3 How the table is used (inferred)

Rows are spreadsheet rows. The first rows of `2og_Q&A.csb` are the authors' notes:
row 2 is the column header (`ソート用ID`, `ID`, `Title`, `Index`, `Question`, `Key Words`,
`Answer`, `画像`, `リンク情報`) and row 0 gives display limits: Title 7 full-width chars at
28 dots, Index and Question 18 chars at 28 dots, Key Words up to 3 lines, Answer 40 chars per
line at 24 dots or 34 at 28 dots, and Answer "サイズが2048まで" (up to 2048 - presumably bytes).
Rows 3+ are the Q&A entries (`<W=24>`, `<C=FF8000FF>`, `<LINK=0>` style tags inside the
text must be kept). `Telop_*`/`Roll_*` rows are timed-effect commands: a command number,
then arguments as strings (`"23","3","eva0004","Dat/logic/Resource/EventAnime/0004"`), with
the credits/telop text as one cell of some rows. `Archive_*` rows are the Archive screen
pages (text cells beside `OG1/1004_1.dds`-style image names). Which column holds text is
not decoded; the worksheet simply lists every string that has a non-ASCII character.

### 1.4 Worksheet

`extract` writes one entry per STRP string that contains a non-ASCII character
(`id` = pool index). Numbers, file names, ids and the column titles stay untouched
(`extract ... --all` lists them too; build accepts any id). Extra keys: `cell` = first
`rNcM` that uses the string, `uses` = number of cells sharing it. Strings are unique in
the pool, so one translation applies to every cell that shares the string.
Counts: Archive_Ending 0, OG1 34, OG2 40, OGg 36, Q&A 400, ScenarioChart 9,
GuidanceSummary 40, Roll_01_cnv 2, Telop_001 7, Telop_002 6, Telop_002_Work2 6,
Telop_003 6 = 586.

---

## 2. WTD (`_DTW`) - window / menu layout trees

Files: `General2d/Dat/Window/WindowToolData/windowdataMain.wtd` (1,614,668 bytes) and
`Logic/Dat/AreaMap2/console/Window/areamapwindow.wtd` (2,544 bytes). Each has a sibling
`.wbp` (sprite/part bank, 8 MB and 10 KB), `Texture/*.dds` and `Ban/*.bnp`. The `.wbp`
holds no reference to a `.wtd` offset or id (checked: none of the 394 element ids and no
element offset occurs in `windowdataMain.wbp`).

### 2.1 Container layout (confirmed)

```
0x00  "_DTW"
0x04  u32 0x10                         (constant in both files)
0x08  u16 FFFF, u16 20                 texture slots
      20 x string                      u32 len (incl NUL) + bytes + pad; empty = u32 0 only
      u16 FFFF, u16 nPal               palette: nPal * 4 * u16 (10000 = 1.0, so 0x2710)
      u16 FFFF, u16 nAnim              nAnim * ( u16 k, u16 total, k * (u16 id, u16 time) )
                                       total = sum of the k times (checked)
      u16 FFFF, u16 nEl                nEl elements, back to back, to EOF
element:  u32 SIZE, SIZE-4 bytes of body.   next element starts at start + SIZE
```

* windowdataMain: textures `tex_01..tex_19` (slot 12, 14, 15, 20 empty), 224 palette quads at
  0xDC, 7 animation tables at 0x7E0, 394 elements from 0x858 to EOF (0x18A34C).
* areamapwindow: textures `imname`, `machine_name`, `machine_name_under` (17 empty), 2
  palette quads, 0 animation tables, 6 elements from 0xA4 to EOF (0x9F0).

**String encoding (confirmed, all 3,386 occurrences):** `u32 len` (including the NUL) +
`len` bytes + zero padding up to the next 4-byte boundary of the **file**. The length word
is always at a 4-aligned file offset. This is the only place a string appears; there is no
string table. Texture names use the same encoding.

### 2.2 Element bodies (decoded; `wtd.py tree FILE [N]`, `wtd.py geometry FILE OUT.json`)

An element is one window: a header with *state lists*, then *groups* of *objects*, each
object a list of *part records*. Every record is a bitmask-driven property list: a `u32 kind`
whose bit n means "property n follows". `parse_element()` in `tools/wtd.py` decodes all
394 + 6 elements exactly to their end (windowdataMain: 1,291 groups, 6,683 objects, 25,601
part records, 824 distinct `kind` values, 2,752 state lists), and every one of the 3,380
scanned text strings is the bit-8 property of a part record. All words are 4-aligned u32/f32;
the earlier guess of 2-byte-aligned u16 fields was wrong.

```
element:  u32 SIZE, u32 id, u32 type (3; 0/1/2/4 rare), s32 -1, u32 (0, or an id in type-1 elements),
          u16 nStates, u16 v,
          nStates x ( u32 k, k x ( u32 objectId, u32 partIndex ) )   state = which part record each object shows
          groups, back to back, until SIZE is used up
group:    u32 id, u16 nObjects, u16 1, f32 x, f32 y, 4 x u32 0, nObjects x object   (x, y) is added to its objects
object:   u32 S (class size 0x40/0x50/0x140/0x158/0x240 ...), u32 id, u32 T (9 = 5,296 of them, 0xD 705, 0xB 450, 1 155),
          4 x u32 (per-T settings, e.g. 0 4 0 1A), s32 -1, string label ("" or the widget id string, e.g. "134"),
          4 x ( u32 n, n x ( u32 hash, u32 id ) )   (event/animation links, nearly always 4 x 0),
          s32 -1, u32 0, u16 nIds, u16 nParts, nIds x u32 id, nParts x part
part:     u32 kind, then the properties whose bit is set, in THIS fixed order (not bit order):
    bit 17  string     always "" where present        bit 18  u32    unknown (0x00030000, 0xFFFE0000, 0)
    bit 0   string     name: kihon_center (most), page, center2_2, dodai, L<R, title_ichiran ...
    bit 1   f32 x      px right of the group origin   bit 14  f32 y  px down from the group origin
    bit 2   f32 w      text: glyph cell width in px (32 = full size); sprite: x scale (1.0)
    bit 15  f32 h      text: glyph cell height in px; sprite: y scale
    bit 3|4 u32 colour ONE word serves both bits: u16 36000/18000/9000 (unknown), u16 palette index 0..223
    bit 5   2 x u32    unknown                        bit 6   u32    link: FFFF NNNN = element index, NNNN FFFF, or -1
    bit 12  u32 hash   id hash ("page" widgets whose text is supplied by code carry this instead of text)
    bit 8   string     DISPLAY TEXT (the worksheet string; may be "")
    bit 9   u32 flags  byte 0 = horizontal alignment 0 left / 1 centre / 2 right (0x10/0x20 also seen);
                       byte 1 = style bits (0x10 nearly always; 0x80, 0x40, 0x20, 0x01..0x04); byte 2 = 0x10/0x20 rarely
    bit 10  u32        small int (4, 1, 17, 384, 400)
    bit 11  u32 n, n bytes padded to 4   typed value: n=4 -> 0x1A or 0x1C, n=1 -> 0, n=0 -> nothing
    bit 16  string     widget id string ("134", "30011", "") - also stored as the object label
```

Part 0 of an object is its **base record** (always named). The records after it are either
sub-sprites (`center2_2` cursor/background at 0,0 scale 1,1) or **alternatives** chosen by
the element's state lists: a delta that carries only the changed properties, e.g.
`kind 0x4102` = x, y, text - the same hint widget showing `：選択` at another x on another
screen. A property missing from a delta is inherited from the base record; missing from the
base as well, the renderer default applies (text: 26 px = the 0.8125 scale seen in game).
`geometry` reports inherited fields per occurrence and lowers the confidence to `medium`.

**Worked example - stat label 格闘** (el33, `wtd.py tree windowdataMain.wtd 33`):

```
030ECC  4236F19B 00080001 41000000 C0000000 0 0 0 0         group 3: id, 8 objects, x=8.0 y=-2.0
031084  00000158 BAA93A2F 00000009 0 0 0 0 FFFFFFFF          object: S=0x158, T=9
0310A4  00000004 "134\0"  0 0 0 0  FFFFFFFF 00000000 00000002  label "134", 4 empty lists, -1, 0, 0 ids / 2 parts
0310C8  0001C117                                            part 0: bits 0 1 2 4 8 14 15 16
0310CC  00000005 70616765 00000000                          name "page"
0310D8  C3A20000  x = -324.0   (+ group 8 = -316)
0310DC  43B80000  y =  368.0   (射撃 400, 技量 432, 防御 464, 回避 496, 命中 528: step 32)
0310E0  41C00000  w =   24.0   glyph cell width  <- the font-size field a build step can change
0310E4  41C00000  h =   24.0   glyph cell height
0310E8  8CA0000B  colour, palette 0x0B
0310EC  00000007 E6A0BCE9 97980000                          text "格闘" (len 7 incl NUL, 1 pad)
0310F8  00000004 31333400                                   bit-16 id string "134"
031100  0001C317 "center2_2" 0 0 1.0 1.0 8CA00000 "" 00100000 ""   part 1: cursor sprite
```

**Worked example - spirit legend cell 熱** (el203; its only group is at (320, 0) with 23 objects):

```
0B4470  00000150 4E28A273 00000001 01000000 0 0 0 FFFFFFFF  00000001 00000000  0 0 0 0  FFFFFFFF 0  00000003
0B44B4  0000C317  0000000D "kihon_center\0" + 3 pad          part 0: bits 0 1 2 4 8 9 14 15
0B44CC  C4070000 x=-540   42840000 y=66   41980000 w=19   41980000 h=19    (魂 -520, 闘 -500 ... 乱 -120: step 20)
0B44DC  8CA00018 colour   00000004 E786B100 "熱"   01800000 flags: byte 0 = 01 -> centred in its 20 px cell
0B44EC  00000010 8CA0000A                                    part 1: colour only (another state)
0B44F4  00008314 41A00000 41A00000 8CA00019 00000001 00000000 01000000   part 2: w=h=20, colour, text "", flags
```

Screen-relative x of the row = 320 + (-540 .. -120) = -220 .. 200, i.e. centred.

**Confirmed vs inferred**

* Confirmed (structural, both files): the grammar above tiles every element to its exact
  end; all 42,158 state-list pairs name an object of their own element with a part index
  below that object's part count; the colour low u16 never exceeds 223 (224 palette quads);
  every text string is a bit-8 property; bits 1/14 are the position pair (deltas that move a
  widget set exactly those two; the six stat labels differ only in bit 14, the legend kanji
  only in bit 1).
* Confirmed against the screenshots: stat labels share x with y step 32; legend kanji share y
  with x step 20 (cells of ~20 px, user estimate ~26); terrain headers 空/陸/海/宇 step 60
  (el36) and 80 (el24); 第 (x=-400) and 話 (x=-346) flank a 28 px number field.
* Inferred: bits 2/15 are the glyph cell size (text records only ever hold 18-32 there,
  sprites hold 1.0; 26 = the renderer's default 0.8125 x 32); flags byte 0 is alignment
  (menu commands 換装/移動/攻撃 at x≈1 carry 01, number fields ９９９ carry 02, long
  messages and はい carry 01, labels carry 00/none); the group origin adds to part
  positions (the legend is only centred with it); y grows downward (header rows have the
  smaller y); 1 unit = 1 px of 1280x720 (95 % of text lies within ±640 x ±360). The window's
  own screen position is applied by code (hint rows sit at y ≈ -430, outside ±360), so x/y
  are relative, not absolute.
* Unknown: colour high u16 (36000/18000/9000), bits 5/10/11/18, flags bytes 1-2, the object
  words after T and the meaning of T, element `type`/word 4/`v`.

`wtd.py geometry FILE OUT.json` writes the worksheet with, per string, `x, y, w, h, scale
(= w/32), align, element, confidence` from its first occurrence plus `occurrences[]` with
every occurrence's element/group/object/part path, inherited fields, `text_w` (chars x w),
`room` (px to the next base record on the same row of the group, null if none) and the
absolute file offsets of the `w`, `h` and `flags` words (`w_offset` ...) so a build step can
patch the font size or alignment. Offsets are valid for the file given; after `build`
changes string lengths, re-run `geometry` on the built file or address records by path.

### 2.3 Does anything besides the string length word change with the string? (confirmed)

**Yes: exactly one field per element - the element's own `SIZE`.** Nothing else.

`SIZE` is the number of bytes from the size word to the start of the next element. It
includes every nested object and every string (the element-size chain of 394 / 6 elements
tiles the file exactly from the first element to EOF, so a wrong `SIZE` would break the
walk). Elements are not nested in one another at this level; each is independent.

Evidence that nothing else depends on string length (`wtd.py audit FILE` re-derives it):

1. **No absolute offsets.** No 4-aligned word of the file equals an element start or end
   (0 hits in either file); 2-aligned reads (words straddling a boundary) give 60 hits, all
   the same two values, 0x4280 (top half of the float 64.0) and 0x65A4, never a real offset. The `.wbp` neighbour never mentions a `.wtd`
   offset. The file header has no file-size or section-size word (the one header word, 0x10,
   is constant; section counts are counts of items).
2. **Inner size-like words are class sizes, not lengths.** The words 0x40/0x50/0x70/0x140/
   0x150/0x240 ... at the start of each of the 5,889 objects are a pure function of
   `(T, count word, kind word)`: 793 distinct classes, 0 with two different values, and in
   118 of those classes the length of the name string that follows varies while the size
   word stays fixed. They match the in-memory struct size of the widget part, e.g. kind
   `0x841` -> 0x40, `0x851` -> 0x50, `0x871` -> 0x70 for every string length.
3. **No redundant length field next to a string.** For every one of the 3,380 non-ASCII
   strings the words within 48 words before/after were compared with `len`, `len-1`, the
   padded size and the character count: no relative position matches more often than the
   baseline (best 8% for `len`, from neighbouring strings; median 2.7%).
4. **Counts are item counts.** The element count (`ffff 018a` = 394), palette and animation
   counts, and the `count` words in objects count items, not bytes.
5. **Built-file test.** `wtd.py selftest FILE` lengthens every distinct string by 1..9
   characters (3..27 bytes, so all four padding cases occur), rebuilds with only the
   string bytes and the 4-byte `SIZE` words changed, then re-parses the output end to end:
   windowdataMain grows 1,614,668 -> 1,668,056 bytes (+53,388), 198 of 394 element sizes
   change, the size chain still tiles the file exactly to EOF, header sections are
   identical, all other bytes of each element are identical, and every string is found
   at its new location with correct length word and zero padding. Same for areamapwindow
   (2,544 -> 2,592, 6 of 6 sizes change).

The full body grammar of 2.2 corroborates this: strings are inline properties, the only
counts are item counts, and no record stores a byte offset or a string length elsewhere.
The built file has not been loaded by the game or RPCS3. If the game misbehaves with a lengthened string, a fixed-size text buffer is a more
likely cause than a missed size field.

### 2.4 Worked example: `areamapwindow.wtd`

```
0000  5f 44 54 57  00 00 00 10                      "_DTW", 0x10
0008  ff ff 00 14                                    20 texture slots
000C  00 00 00 07 69 6d 6e 61 6d 65 00 | 00           len 7 "imname\0", 1 pad byte
0018  00 00 00 0d "machine_name\0" 00 00 00           len 13, 3 pad (next len at 0x2C)
002C  00 00 00 13 "machine_name_under\0" ...           len 19, 1 pad; then 17 x 00 00 00 00
0088  ff ff 00 02  + 2 * 8 bytes                       2 palette quads (27 10 = 1.0)
009C  ff ff 00 00                                      0 animation tables
00A0  ff ff 00 06                                      6 elements
00A4  00 00 01 f4 4e 17 38 a7 ...                      element 0: size 0x1F4 -> next at 0x298
0298  00 00 01 88 95 22 80 df ...                      element 1: 0x188 -> 0x420
0420  00 00 01 90 ...                                  element 2: 0x190 -> 0x5B0
05B0  00 00 01 88 ...    0738  00 00 01 88 ...         elements 3, 4 -> 0x8C0
08C0  00 00 01 30 3c 6f 4b 13 ...                      element 5: 0x130 -> 0x9F0 = EOF
```

Element 5 holds the text `伊豆基地` (Izu base) at 0x9CC:

```
09CC  00 00 00 0d  e4 bc 8a e8 b1 86 e5 9f ba e5 9c b0  00  00 00 00
      len=13       12 UTF-8 bytes (4 chars)              NUL  3 pad  -> 20 bytes, next field at 0x9E0
```

Replace it with `Izu Base Camp Alpha`: `00 00 00 14` + 19 bytes + NUL, no padding = 24 bytes, so
everything after it moves +4 and element 5's size word changes `00 00 01 30` -> `00 00 01 34`.
Nothing else in element 5 changes. (The same text also occurs in element 1, which grows
too; replace-all gives the 2,552-byte file `wtd.py build` writes.)

### 2.5 Worksheet

Default (and only) mode: strings containing a non-ASCII character, i.e. display text such as
`：決定`, `機体一覧`, `＜補給＞　味方の機体を選択します`. Everything else is recorded as untouched
and never rewritten: ASCII-only strings (widget and texture ids: `kihon_center` x4,425,
`page`, `L<R`, `center2_2`, `title_ichiran`, texture names, plain numbers, `<I=61>` tag
strings) and all non-text data. The scan rule: 4-aligned length word, NUL-terminated, valid
UTF-8 with at least one non-ASCII character, no control characters other than `\n`, no
code points U+0100..U+1FFF (rejects one hash word in windowdataMain that looks like a
string), zero padding, entirely inside an element body. A byte scan for kana/CJK sequences
outside the recognised strings finds only floats and hash words (e.g. `e9 a5 9a` in the
repeated id `xx e9 a5 9a`), no stray text.

The same text is repeated over and over in the widget tree (3,380 occurrences in
windowdataMain, 990 distinct texts; 6 and 4 in areamapwindow), so the worksheet has one
entry per distinct text with `count` = occurrences, and `build` replaces every occurrence of
`jp` with `en`. The earlier estimate of ~775 Japanese strings was lower than the 990 found
here; the difference is mostly short symbol/label strings such as `：戻る`.

---

## 3. Worksheet summary

| file | strings |
|---|---|
| Common/Dat/Archive/Csb/Archive_Ending.csb | 0 |
| Common/Dat/Archive/Csb/Archive_OG1.csb | 34 |
| Common/Dat/Archive/Csb/Archive_OG2.csb | 40 |
| Common/Dat/Archive/Csb/Archive_OGg.csb | 36 |
| Common/Dat/Option/QA/2og_Q&A.csb | 400 |
| Common/Dat/Option/ScenarioChart/ScenarioChart.csb | 9 |
| Logic/Dat/logic/Resource/summary/2og_GuidanceSummary.csb | 40 |
| Logic/Dat/Roll/Csb/Roll_01_cnv.csb | 2 |
| Logic/Dat/Roll/Csb/Telop_001.csb | 7 |
| Logic/Dat/Roll/Csb/Telop_002.csb | 6 |
| Logic/Dat/Roll/Csb/Telop_002_Work2.csb | 6 |
| Logic/Dat/Roll/Csb/Telop_003.csb | 6 |
| General2d/Dat/Window/WindowToolData/windowdataMain.wtd | 990 (3,380 occurrences) |
| Logic/Dat/AreaMap2/console/Window/areamapwindow.wtd | 4 (6 occurrences) |
| **total** | **1,580** |

## 4. Open questions

* No built file has been run in the game or RPCS3 yet. Whether the game accepts a longer
  WTD or CSB (memory pools, fixed text buffers, display-width limits) is untested; the
  Q&A authors' notes give per-column character limits (section 1.3), the WTD limits are
  unknown.
* WTD element bodies are not fully decoded, so "SIZE is the only dependent field" rests on
  the structural evidence in 2.3 rather than a complete grammar.
* `Telop_002_Work2.csb` has the same size and structure as `Telop_002.csb` but different cell
  values; it may be an unused work copy.
* In `2og_Q&A.csb` rows 0-2 are author notes, probably never displayed; they are in the
  worksheet only because they contain Japanese.
