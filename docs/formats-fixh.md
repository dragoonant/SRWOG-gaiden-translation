# FIXH fixed-data containers (`Logic/Dat/FixedData/*.dat`)

Game: 2nd Super Robot Wars OG, PS3, BLJS10133. 26 files, all big-endian, all starting with
`FIXH`. Tool: `tools/fixh.py` (`info`, `dump`, `extract`, `build`, `roundtrip`).

Status: `python -I fixh.py roundtrip <dir>` rebuilds all 26 files byte-for-byte from their
extracted JSON (4603 strings). Everything marked **confirmed** below is exercised by that
round trip or checked programmatically across every file; **inferred** means it is a reading
of the data that has not been checked against the EBOOT.

## 1. File layout

```
offset  size  content
0x00    4     "FIXH"
0x04    4     u32 8            (header length? constant in all 26 files)
0x08    4     u32 0xFEFF0000   (byte-order mark, constant)
0x0C    4     u32 0x00010000   (version 1.0, constant)
0x10    ...   sections, back to back, in the order DOFS? DATA SOFS STRI
```

Sections (**confirmed**):

| magic | header | payload | notes |
|---|---|---|---|
| `DOFS` | `magic(4) size(4)` | `u32[size/4]` | id -> record index. `0xFFFFFFFF` = no record for that id. Optional (13 of 26 files). |
| `DATA` | `magic(4) size(4) count(4)` | `count` fixed-size records | record size = `size / count`. Present in every file. |
| `SOFS` | `magic(4) size(4)` | `u32[size/4]` | byte offset of each string entry, relative to the start of the STRI payload. One per string. |
| `STRI` | `magic(4) size(4) count(4)` | string entries | `count` = number of strings = SOFS entries. Payload is padded with NUL to a multiple of 4 bytes (0..3 pad bytes). |

* `size` is the payload length only: it excludes the 8- or 12-byte section header, and for
  DATA/STRI it excludes the `count` word. Next section starts at `payload_start + size`.
* DOFS and SOFS carry no count word; their entry count is `size / 4`.
* Files with no strings still carry `SOFS size=0` and `STRI size=0 count=0`
  (CombineData, ExUnitData, ExtraPilotData, FavoritePilotData, FavoriteRobotData).
* `TROP`, `CLEA`, `SPEC` are **not** section magics: they are the first bytes of the
  trophy internal-id strings (`TROPHY_OG_MASTER`, `TROPHY_EX_HARD_CLEAR` ...) inside
  TrophyData's STRI.

Worked example, `AntiFieldTypeData.dat` (168 bytes), whole file:

```
0000  46495848 00000008 FEFF0000 00010000   FIXH header
0010  44415441 00000010 00000004            DATA size=0x10 count=4   -> 4 records of 4 bytes
001C  00000000 0101025C 0202025D 0303025E   records (id, name string idx, help id)
002C  534F4653 00000010                     SOFS size=0x10           -> 4 offsets
0034  00000000 0000002E 0000003B 00000048   string entry offsets inside STRI payload
0044  53545249 00000058 00000004            STRI size=0x58 count=4
0050  0001 000D 0000  EFBC8D x13  00        entry 0: 1 line, 13 chars, "－－－－－－－－－－－－－"
007E  0001 0002 0000  E784A1 E58AB9 00      entry 1: "無効"
008B  0001 0002 0000  E8B2AB E9809A 00      entry 2: "貫通"
0098  0001 0002 0000  E5BCB1 E4BD93 00      entry 3: "弱体"
00A5  00 00 00                              pad to 4-byte boundary (0xA8 = file end)
```

## 2. STRI string entry (**confirmed**)

```
u16 line_count
line_count x { u16 char_count ; u16 byte_offset }
line_count x ( UTF-8 bytes, NUL )          packed back to back, no padding between lines
```

* `byte_offset` is relative to the first text byte, i.e. `entry + 2 + 4*line_count`.
  Line k's offset is always the sum of the preceding lines' (bytes + 1).
* `char_count` is the number of Unicode code points in the line (verified for all 5,000+
  lines; the builder recomputes it with `len(str)`).
* A "line" is a display line of the game's text box; multi-line entries are common in
  descriptions and dictionary text (up to 26 lines in UnitDictionaryData). Some single
  lines contain a literal `\n` (MapWeaponData grid pictures) - that is content, not a
  line break of this format, so the JSON uses `lines` for those too.
* Text is UTF-8. Mostly full-width characters; ASCII only in file names and internal ids.

Multi-line example, `ACEBonusData.dat` entry 1 at file offset 0x18D8 (STRI payload 0x18A4 +
SOFS[1] = 0x34):

```
0002                       2 lines
000F 0000                  line 0: 15 chars at +0
000F 002E                  line 1: 15 chars at +0x2E (= 15*3 + 1)
E68FB4 ... EFBC85 00       "援護攻撃の最終ダメージ＋１０％" NUL
E68FB4 ... EFBC85 00       "援護防御の最終ダメージ－２０％" NUL
```

## 3. DOFS (**confirmed** for all 13 files that have it)

`DOFS[id] == record_index` for every record, where `id` is the record's first field
(u8 at +0 in BGM/Combine/ExUnit/Parts/Stage, u16 at +0 in Help/KeyGuide/KeyWord/Pilot/
PilotDictionary/Unit/UnitDictionary). Entries of `0xFFFFFFFF` are ids with no record
(PilotData 20 holes, UnitData 10, StageData 103). Records are usually stored in id order,
but StageData is not, so DOFS must be used rather than assumed to be the identity.
The builder copies DOFS verbatim (string edits never change it).

## 4. How records reference strings

Every record field that holds a string index is listed in `FIELD_MAP` in `fixh.py` and
printed by `fixh.py info`. The map was derived by hand from hex dumps, then checked
programmatically: every value of every listed field is `< string_count`, and the union of
the listed fields references 4585 of the 4603 strings (the remaining 18 are orphans, see
section 6). The field positions are therefore **confirmed as consistent with the data**;
their *meaning* (name / description / comment) is **inferred** from the text.

Index width: u8 in files with < 256 strings, u16 (big-endian) in PilotData, UnitData,
WeaponData and HelpData (these have 538-753 strings). In ACEBonusData the one-line text
field could equally be `u16 @+0x2C`; the value is the same either way.

| file | records x size | strings | string-index fields (offset in record) | other identified fields |
|---|---|---|---|---|
| ACEBonusData | 116 x 48 | 173 | `u8 +1` bonus text, 2-line version; `u8 +45` same text as one line | `u8 +0` id |
| AbilityData | 56 x 12 | 96 | `u8 +1` name; `u8 +2` name_b (same as +1 except recs 12-17); `u8 +10` description | `u8 +0` id; `u16 +6`, `u16 +8` HelpData id |
| AbilityElementData | 22 x 56 | 44 | `u8 +1` name; `u8 +54` description | `u8 +0` id; `u16 +50`, `u16 +52` HelpData ids |
| AntiFieldTypeData | 4 x 4 | 4 | `u8 +1` name | `u8 +0` id; `u16 +2` HelpData id |
| BGMData | 242 x 8 | 217 | `u8 +1` title | `u8 +0` id (DOFS); `u16 +2` BGM number? |
| HelpData | 769 x 4 | 753 | `u16 +2` text | `u16 +0` id (DOFS). Other files store HelpData ids (0x1xx-0x2xx) that resolve through DOFS here. |
| KeyGuideData | 130 x 100 | 191 | 12 button slots of 8 bytes starting at +4: `u8 slot+6` short label, `u8 slot+7` long label | `u16 +0` id; per slot `i16 x, i16 y, u16 ?` (x = -10000 (0xD8F1) when unused) |
| KeyWordData | 65 x 8 | 130 | `u8 +2`, `u8 +3`, `u8 +4` keyword (three identical copies); `u8 +5` description (multi-line) | `u16 +0` id |
| MAXChangeBonusData | 108 x 60 | 207 | `u8 +1` name; `u8 +56` description | `u8 +0` id |
| MapWeaponData | 18 x 4 | 22 | `u8 +2` range picture (■□◎ grid, `\n`-separated); `u8 +3` type label | `u16 +0` id |
| PartsData | 44 x 64 | 88 | `u8 +1` name; `u8 +62` description | `u8 +0` id (DOFS); `u16 +60` HelpData id |
| PilotData | 316 x 288 | 642 | `u16 +2` name (list/short); `u16 +4` **developer comment**; `u16 +12` full-name part 2 (surname); `u16 +14` full-name part 1; `u16 +0x100` voice actor | `u16 +0` id (DOFS); `u16 +6` sort key (unique per record) |
| PilotDictionaryData | 197 x 4 | 178 | `u8 +2` biography text (multi-line) | `u16 +0` id (DOFS) |
| SkillData | 44 x 32 | 87 | `u8 +1` name; `u8 +28` description | `u8 +0` id; `u16 +26` HelpData id |
| SpecialEffectData | 14 x 20 | 14 | `u8 +1` name | `u8 +0` id; `u16 +2..` HelpData ids |
| SpiritData | 44 x 12 | 88 | `u8 +1` name; `u8 +10` description | `u8 +0` id |
| StageData | 98 x 16 | 110 | `u8 +2` title; `u8 +3` subtitle (always ''); `u8 +4` title_b (= title except record 0: 'プロローグです。'); `u8 +5` route name; `u8 +13` route icon file name | `u8 +0` id (DOFS) |
| TrophyData | 40 x 12 | 160 | `u8 +4` name; `u8 +5` description; `u8 +6` internal id (`TROPHY_*`); `u8 +10` image path | `u16 +0` index; `u16 +2` trophy number (0x190+) |
| UnitData | 250 x 180 | 538 | `u16 +2` name; `u16 +4` **developer comment**; `u16 +0xA8` height ('１９．１ｍ'); `u16 +0xAA` weight | `u16 +0` id (DOFS); `u16 +6` sort key |
| UnitDictionaryData | 223 x 4 | 188 | `u8 +2` description text (multi-line) | `u16 +0` id (DOFS) |
| WeaponData | 998 x 80 | 673 | `u16 +4` name; `u16 +6` **developer comment** | `u8 +2` id? ; many stat fields not decoded |
| CombineData | 53 x 16 | 0 | - | DOFS identity |
| ExUnitData | 7 x 12 | 0 | - | DOFS identity |
| ExtraPilotData | 2 x 8 | 0 | - | |
| FavoritePilotData | 1891 x 8 | 0 | - | |
| FavoriteRobotData | 1061 x 8 | 0 | - | |

Non-string record fields (stats, flags) are not decoded; the builder never touches them.

Worked example, `SpiritData.dat` record 2 (DATA payload 0x1C + 2*12 = 0x34):

```
0034  02 04 0071 0201 1500 02 15 05 00
      ^  ^                       ^
      |  +1 = 4  -> string 4 "偵察"            (name)
      +0 = 2 id                  +10 = 5 -> string 5 "指定した敵ユニットの..." (description)
SOFS[4] = 0x43, SOFS[5] = 0x50; STRI payload at 0x3A0:
03E3  0001 0002 0000 E581B5 E5AF9F 00          "偵察"
03F0  0001 001B 0000 E68C87 ... E38082 00      27 chars, "指定した敵ユニットのステータスを調べることができます。"
```

Worked example, `PilotData.dat` record 2 (Masaki): `0002 0004 0001 010E 03E8 FFFF 0005 0004 ...`
-> id 2, name = string 4 "マサキ", comment = string 1 "", full-name part 2 = string 5
"アンドー", part 1 = string 4 "マサキ" (full name "マサキ・アンドー"); `+0x100` = 6 "緑川光"
(voice actor). Record 98's comment field points at string 315 "男主人公。エール・シュヴァリアー、…".

## 5. Developer comments vs display text (**inferred** from content)

The `comment` fields (PilotData +4, UnitData +4, WeaponData +6) hold text such as
'男主人公。…', '敵用。デュラクシール', '味方用', '使用禁止', 'イベント用', '敵でも使う可能性あり',
'新換装武器', and weapon categories like '実弾'/'ビーム'/'マップ兵器'. Nothing like it appears in
the game UI, so these are treated as developer notes that the game never displays:
PilotData 111, UnitData 94, WeaponData 60 strings (265 total). `extract` tags them
`role: "comment"`; they can be left in Japanese. WeaponData's comment field also carries
kana readings of some kanji weapon names ('しゅらけん'); whether anything sorts on them is
unknown.

`role: "internal"` = identifiers and paths (TrophyData `TROPHY_*` ids and `image\...png`,
StageData `icon_route_*.png`): do not translate. `role: "orphan"` = referenced by no record
(18 strings: 'ＤＵＭＭＹ' placeholders, a removed pilot 'ロレンツォ' / 'ディ・モンテニャッコ',
KeyGuide 'button_0', 13 stray WeaponData comments). `role: "unknown"` = StageData record 0
title_b 'プロローグです。'.

PilotData `voice_actor` (115 distinct names) is tagged display because the character
dictionary in this series shows CV credits, but that has not been verified in this game.

## 6. Counts

| file | strings | display | comment | internal | orphan |
|---|---|---|---|---|---|
| ACEBonusData | 173 | 173 | | | |
| AbilityData | 96 | 96 | | | |
| AbilityElementData | 44 | 44 | | | |
| AntiFieldTypeData | 4 | 4 | | | |
| BGMData | 217 | 217 | | | |
| HelpData | 753 | 753 | | | |
| KeyGuideData | 191 | 190 | | | 1 |
| KeyWordData | 130 | 130 | | | |
| MAXChangeBonusData | 207 | 207 | | | |
| MapWeaponData | 22 | 22 | | | |
| PartsData | 88 | 88 | | | |
| PilotData | 642 | 528 | 111 | | 3 |
| PilotDictionaryData | 178 | 178 | | | |
| SkillData | 87 | 87 | | | |
| SpecialEffectData | 14 | 14 | | | |
| SpiritData | 88 | 88 | | | |
| StageData | 110 | 106 (+1 unknown) | | 3 | |
| TrophyData | 160 | 80 | | 80 | |
| UnitData | 538 | 443 | 94 | | 1 |
| UnitDictionaryData | 188 | 188 | | | |
| WeaponData | 673 | 600 | 60 | | 13 |
| Combine/ExUnit/ExtraPilot/FavoritePilot/FavoriteRobot | 0 | | | | |
| **total** | **4603** | 4236 | 265 | 83 | 18 |

## 7. Inline fixed-width text

None. Every DATA payload was scanned for UTF-8 multi-byte sequences and for ASCII runs:
no text is stored inline in any of the 26 files; the names and comments seen in
PilotData/UnitData/WeaponData are ordinary STRI strings (those three files do have
SOFS/STRI sections, at the end of the file). `fixh.py` nevertheless implements inline
fields (`INLINE_FIELDS`, `inline_strings` in the JSON, zero padding, overflow error, field
width recorded as the budget) so a file that uses them can be added by a one-line table entry.

## 8. Rebuilding (`fixh.py build`)

Input: the original `.dat` plus the JSON from `extract` with edited `text` / `lines`.
Output = FIXH header + sections in original order: DOFS copied verbatim; DATA copied verbatim
(records keep their string indices, so the string count must not change); SOFS and STRI
regenerated (offsets, char counts, 4-byte NUL padding). Byte budget: strings are variable
length; the only hard limits are the u16 header fields (65535 code points per line, 65535
bytes of text per entry). No on-screen width is encoded in the file - that has to come from
the renderer (EBOOT), see the open questions.

## 9. Open questions

1. Whether the game reads `char_count` for layout (it is code points; English text will have
   more, narrower characters per line than the Japanese it replaces).
2. On-screen width per field (name columns, help boxes, dictionary pages) - not in the file.
3. Confirm in the EBOOT that the `comment` fields are never rendered, and whether
   `voice_actor` is shown.
4. Purpose of the duplicate name fields (AbilityData +2, KeyWordData +3/+4, PilotData +2 vs
   +14, StageData +4) - which copy the game shows.
5. Meaning of the remaining numeric fields (u16 +6 sort keys, BGM numbers, trophy numbers,
   KeyGuide x/y) - not needed for text but useful if sort order by kana must be re-done for
   English.
6. ACEBonusData one-line text index: `u8 +45` or `u16 +44` (same value).
