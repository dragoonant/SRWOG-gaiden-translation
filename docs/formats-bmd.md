# BMD battle-quote files (`Battle/Dat/Battle/Message/NNN.bmd`)

Game: 2nd Super Robot Wars OG, PS3, BLJS10133. 307 files (`000.bmd` .. `305.bmd` plus
`999.bmd`; the directory also holds a 40-byte `bmdExist.bin` which is not a BMD). One file
per pilot: `NNN` is the pilot id and it is the `speaker` of almost every line in the file
(`002.bmd` = Masaki, `190`/`191` = Kuro/Shiro, `063.bmd` = pilot 63 ...). 90 files are 948-byte
stubs holding only `「………」`. Smallest file `001.bmd` (944 bytes), largest `063.bmd`
(72060 bytes). All big-endian; text is UTF-8, NUL-terminated. Tool: `tools/battle.py`
(`info`, `dump`, `extract`, `build`, `roundtrip`, `stats`).

Status: `python -I battle.py roundtrip <dir>` rebuilds all 307 files byte-for-byte from their
extracted JSON (34616 pool strings, 59297 line records). Everything marked **confirmed**
below is exercised by that round trip or checked programmatically across every file;
**inferred** is a reading of the data that has not been checked against the EBOOT.

## 1. File layout (**confirmed**)

```
offset             size        content
0x00               2           u16 0x0100          version (constant in all 307 files)
0x02               2           u16 A               number of groups
0x04               2           u16 B               number of entries
0x06               2           u16 C               number of lines
0x08               12*A        group table
0x08+12*A          16*B        entry table
0x08+12*A+16*B     16*C        line table
0x08+12*A+16*B+16*C  ...       string pool: UTF-8 NUL-terminated strings, back to back
end                0..3        NUL padding so the file length is a multiple of 4
```

There is nothing after the pool: `file_length = pool_start + pool_bytes + pad`, with
`pad = (-(pool_start + pool_bytes)) mod 4`, checked on every file. The padding bytes are
always zero (no garbage to preserve). There are no section magics, no offset table, and no
file-size field; the three counts determine every table position.

The three tables form a tree: a **group** (situation or weapon) owns a contiguous run of
**entries**; an entry (one "choice" of what to say) owns a contiguous run of **lines**; a
line carries the speaker, voice and the pool offset of its text. Runs are always
contiguous and in order (`first` of each record equals the running sum of the previous
counts; the counts sum exactly to `B` resp. `C`). Lines are chosen among the entries of a
group at run time; an entry with two or more lines is a short exchange (e.g. Kuro warns
Masaki, Masaki replies).

### Group record, 12 bytes (**confirmed layout**)

| off | type | field | notes |
|---|---|---|---|
| 0 | u16 | type | 0 = situation, 1/2/3/4/15 = weapon-class (see below) |
| 2 | u16 | id | situation id for type 0, weapon id otherwise |
| 4 | u16 | zero | always 0 |
| 6 | u16 | flag | 0 for the base situations (type 0, id 0..21); 1 for every other group (also the type-0 "event" groups with id >= 30) |
| 8 | u16 | count | number of entries |
| 10 | u16 | first | index of the first entry in the entry table |

### Entry record, 16 bytes (**confirmed layout**, meanings inferred)

| off | type | field | notes |
|---|---|---|---|
| 0 | u8 | kind | 0 plain, 1 vs a specific pilot (`target` = pilot id), 2 vs pilot (second form: `target` + `c5`), 3 support/assist line (group 16/17), 4 crew conversation (`target` = 0x81/0x82 ...), 5 rare (death screams with `target` ~0x19C8..0x2008) |
| 1 | u8 | weight | 100 in 51642 of 52648 entries; also 120, 50, 40, 20, 10, 60. Looks like a selection priority / percentage (inferred) |
| 2 | u16 | count | number of lines |
| 4 | u16 | first | index of the first line in the line table |
| 6 | u16 | target | condition: pilot id (kind 1/2/3), unit/crew id (kind 4), 0 = none |
| 8 | u16 | c4 | usually 0; otherwise a second id (e.g. 0x2711..0x2714, 417, 10003) |
| 10 | u16 | c5 | usually 0; otherwise a pilot id (45, 90, 46, 74, 230 ...) |
| 12 | u16 | c6 | 0, 0xFFFF, or 1..10 = attack phase / sequence number within a weapon group (inferred) |
| 14 | u16 | c7 | bit flags: 1, 2, 4, 8, 0x20, 0x40, 0x80, 0x100, 0x200, 0x400 and a few combinations |

### Line record, 16 bytes (**confirmed layout**)

| off | type | field | notes |
|---|---|---|---|
| 0 | u16 | zero | always 0 (59297 of 59297) |
| 2 | u16 | speaker | pilot id. Equals the file number for the main speaker; sub-pilots / partners appear too (002: 2, 190, 191; 063: 63, 64, 65; 107: 107, 108) |
| 4 | u16 | face | portrait / expression index 0..22, or 256..261 (high bit set, probably an alternate portrait set) |
| 6 | u16 | zero | always 0 |
| 8 | u16 | voice_bank | 0..43; constant per speaker within a file in almost every case (inferred: voice archive index) |
| 10 | u16 | voice_id | 26938 distinct values; a per-line clip id (0 / 10000 / 10001 in stub lines) |
| 12 | u16 | name_off | pool offset of a speaker-name override string, 0xFFFF = none |
| 14 | u16 | text_off | pool offset of the line text |

**Pool addressing (confirmed):** both offsets are byte offsets relative to the start of the
pool, not absolute, not indices. They are 16-bit; the largest pool is 35287 bytes
(`063.bmd`) so this is never a problem for the originals, but a translation that pushes a
pool past 65535 bytes cannot be encoded (`build` refuses). Every pool string is referenced
by at least one `text_off` or `name_off` (there are no orphan strings; the strings that
looked unreferenced at first were the `name_off` targets). Identical texts are stored once
and shared: `002.bmd` has 686 lines but only 492 pool strings. The pool is in first-use
order except for the name-override strings, which the compiler emitted first
(`106.bmd`, `107.bmd`, `098.bmd`, `248.bmd`, `305.bmd`), and `106.bmd` where a couple of
strings are out of order; `build` keeps the original pool order, so this does not matter.

Only four name overrides exist in the whole set: `？？？` (098, 248), `リム` (106, 107),
`所属不明兵` (305) and `　　　　` (045). They display instead of the speaker's pilot name
(inferred from the content).

Text conventions: full-width characters throughout. The in-quote line break is `/`
(5456 occurrences; the only ASCII character that appears in any pool string), normally
followed by U+3000 to indent the continuation line, e.g.
`「ちきしょう！/　このままじゃやられちまうぜっ！」`. The `@` line break of the scenario
scripts does **not** occur in BMD files. There are no empty strings.

## 2. Group types and situation ids (inferred from content)

Type 0 groups with `flag 0` are the 22 base situations, present in every file (id 21 in 188
files, id 1 in 290). Judging from `002.bmd` (Masaki):

| id | first line in 002 | reading |
|---|---|---|
| 0 | 「遅いっ！！」 | attack |
| 1 | 「やりやがったなっ！！」 | hit (took damage, still fine) |
| 2 | 「ちっ！！/　オレもヤキがまわったもんだぜ！！」 | destroyed |
| 3 | 「ちきしょう！/　このままじゃやられちまうぜっ！」 | heavy damage |
| 4 | 「ちっ！！　やるじゃねえかっ！！」 | hit by enemy attack |
| 5 | 「ヘッ、こっちのスピードに/　追いつきやがったか！」 | hit while evading? |
| 6 | 「狙いが甘いぜ！！」 | enemy missed |
| 7 | 「バーカ、もっとよく狙いな！」 | evade |
| 8..11 | 「へん、その程度かよ！」 / 「フン、効かねえぜ！」 | damage blocked / no effect |
| 12 | 「………」 | silent |
| 13 | 「くそっ！　弾切れになっちまった！！」 | out of ammo |
| 14 | 「ちっ！　こっからじゃ届かねえ！！」 | out of range |
| 15 | 「使える武器がねえだと！？」 | no usable weapon |
| 16 | 「どこ見てんだ！　隙だらけだぜ！！」 | support attack (kind 3 entries name the supported pilot) |
| 17 | 「させるかよっ！！」 | support defend |
| 18,19 | 「まとめて片づけてやるぜ！」 | MAP / all-range attack |
| 20 | 「もう一撃、叩き込んでやる！」 | follow-up attack |
| 21 | 「行くぜ、サイバスター！」 | unit intro / first attack |

Type 0 groups with `flag 1` and `id >= 30` (30, 31, 40, 41, 2010 .. 65040) occur in a few
files each; the ids look like `scenario*1000 + event` (2030/2031 in 31 files, 35030 ...)
and hold scenario-specific or combination-attack lines (inferred).

Types 1, 2, 3, 4 and 15 carry a **weapon id** in `id` and hold the lines spoken when that
weapon is used (`「いけぇっ！　カロリックミサイル！！」` for id 64464 = 0xFBD0). Weapon ids
come in runs of 10 (64464, 64474, 64484 ...), the different types probably select the id
table the number refers to (unit weapon table vs. shared tables); not verified.

## 3. Worked example: `002.bmd` (49900 bytes)

Header and first group:

```
00000000: 0100 0025 0237 02ae  version 0x0100, A=37 groups, B=567 entries, C=686 lines
00000008: 0000 0000 0000 0000 0091 0000   group 0: type 0, id 0, 0, flag 0, 145 entries from 0
00000014: 0000 0001 0000 0000 000c 0091   group 1: type 0, id 1, 12 entries from 145
...
00000110: 0001 fbd0 0000 0001 0001 0205   group 22: type 1 (weapon) id 0xFBD0, flag 1, 1 entry from 517
```

Table positions: entries at `0x08 + 12*37 = 0x1C4`, lines at `0x1C4 + 16*567 = 0x2534`,
pool at `0x2534 + 16*686 = 0x5014`.

```
000001c4: 0064 0001 0000 0000 0000 0000 0000 0000   entry 0: kind 0, weight 100, 1 line from 0
00000284: 0464 0002 000c 0082 0000 0000 0000 0000   entry 12: kind 4 (crew), w100, 2 lines from 12, target 0x82
000004e4: 0164 0001 003c 2350 0000 0025 ffff 0200   entry 50: kind 1 (vs), target 9040, c5=37, c6=0xFFFF, c7=0x200
```

```
00002534: 0000 0002 0001 0000 0000 4e3d ffff 0000   line 0: speaker 2 (Masaki), face 1, bank 0, voice 20029,
                                                      no name, text @0 -> 「遅いっ！！」
000025f4: 0000 00be 0001 0000 001c fdef ffff 01b3   line 12: speaker 190 (Kuro), face 1, bank 28, voice 65007,
                                                      text @0x1B3 -> 「マサキ、敵が来るニャ！」
00002604: 0000 0002 0000 0000 0000 4e61 ffff 01db   line 13: Masaki replies 「ああ、わかったぜ！」
```

Pool start and end:

```
00005014: e380 8ce9 8185 e381 84e3 8163 efbc 81ef   「遅いっ！！」  (0x16 bytes incl. NUL; line 1 points at @0x16)
...
0000c2e4: 81e3 808d 00 | 00 00 00                   last string's NUL at 0xC2E8 (pool = 29397 bytes),
                                                      then 3 NUL pad bytes -> file length 49900 = 0xC2EC
```

Name override, `305.bmd` line 0 at `0xAF4`:

```
00000af4: 0000 0131 0001 0000 0017 589f 0000 09c0   speaker 305, face 1, bank 23, voice 22687,
                                                      name_off 0 -> 「所属不明兵」, text_off 0x9C0 -> 「くらえ！」
000014b4: e689 80e5 b19e e4b8 8de6 988e e585 b500   pool starts with the 16-byte name string
```

Stub file `001.bmd` (944 bytes): A=B=C=21, 21 groups (situations 0..20, one entry, one
line each), all 21 lines are `0000 0001 0000 0000 0000 2710 ffff 0000` (speaker 1, voice
10000, text @0 = `　　　`), pool is 10 bytes at `0x3A4`, 2 pad bytes.

## 4. Rebuilding

`battle.py build ORIGINAL IN.json OUT` re-serialises the header and the three tables from
the parsed records, re-emits the pool in the original order with every string replaced
by its `en` text (falling back to `jp`), recomputes `text_off` / `name_off` through an
old-offset -> new-offset map, and appends the 0..3 NUL pad bytes. Table sizes never change
(the translation changes strings, not records), so only the pool and the two offset fields
move. Constraints enforced: no NUL inside a string, pool <= 65535 bytes, the JSON must have
the same number of strings as the original and matching `jp` texts.

JSON produced by `extract`: `{"file", "format": "BMD", "counts", "strings": [...]}` with
one object per pool string: `id` (pool order), `offset`, `role` (`text`, `name` or
`text+name`), `speakers`, `jp`, `en`, and `refs` = every line that uses the string with
its line / entry index, `[group type, group id]`, entry kind / weight / target, speaker,
face and `[voice_bank, voice_id]`. Since strings are shared, translating one JSON entry
changes every line that uses it (a line with a different context can't be split without
adding a pool string; the builder does not support that yet - see open questions).

## 5. Open questions

* Meanings of entry `weight` (100/120/50/...), `c4`, `c5`, `c6`, `c7` are inferred from
  patterns only; `c7` is clearly a bitmask and `c6` a phase index inside multi-phase
  weapon groups, but which code reads them is unknown.
* `face` 256+ and `voice_bank` are not matched against the portrait / voice archives.
* The type-0 `flag 1` groups with 5-digit ids (scenario events) and the relation between
  weapon-group types 1/2/3/4/15 and the unit weapon tables need the unit data to confirm.
* `bmdExist.bin` (40 bytes, `FFFF` x 18, `0003`, `FFFF`) sits beside the BMDs; it is not a
  BMD and its role is unknown.
* `build` keeps one pool string per original string. If a shared Japanese line needs two
  different English renderings (same text, different speakers), the builder would have to
  append a new pool string and repoint individual lines; this is a small extension
  (16-bit offsets allow it) but is not implemented.
