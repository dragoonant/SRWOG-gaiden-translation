# Deviations: OGs patch vs Akurasu

The OGs PS2 fan patch (`ogs.xdelta`) is the translation basis. Akurasu's 2nd OG pages are the reference it should agree with. This file lists every place the two disagree, so you can pick one. Until you decide, `glossary/signoff.tsv` uses the OGs form; its `ogs` and `akurasu` columns hold both.

How the OGs text was read: the patch's added data was decoded without the original disc (`tools/xdelta_added.py`), which recovers the English script and data tables, about 140,000 strings. Names were matched against that text (`tools/ogs_compare.py`).

## Coverage of the 1,140 data-table names

| Source of the current English | Names |
|---|---|
| Found in the OGs patch | 355 |
| Not in OGs, Akurasu has an exact JP/EN pair | 113 |
| Neither; earlier proposal (217 of these came from Akurasu's English-only pages) | 672 |

Of the names found in both, 120 agree and 50 differ (tables below).

## Honorifics (decided from the OGs patch)

Across 53,168 dialogue lines the OGs patch uses no -san, -kun, -chan, -sama, -dono, senpai or nee-san. The only honorific kept is **Rishu-sensei** (21 lines). Characters use English ranks and roles written out in full: Captain (601), Lieutenant (640, never "Lt."), Commander (320), sir (782), Master (94), Doctor (30), Sis (18).

Decision for 2nd OG: drop honorifics; keep "Rishu-sensei" where the Japanese has it; ranks in full. `docs/style-guide.md` is updated to match.

## Patterns behind most deviations

- **Long vowels.** OGs drops the long "u": Kyosuke, Ryusei, Shu, Rishu, Kota, Shoko, Hiryu. Akurasu 2nd OG writes Kyousuke, Ryuusei, Shuu, Rishuu, Kouta, Shouko, Hiryuu.
- **German names keep umlauts in OGs:** Lüne, Sänger, Rätsel, Wildwürger. Akurasu: Ryuune, Sanger, Ratsel, Wildwurger. Font check: the 2nd OG font has a glyph for ä but none for ü, ö or é. So Sänger and Rätsel work as-is; Lüne and Wildwürger need a ü glyph added to the font (possible, we have the format) or the plain spellings Lune and Wildwurger.
- **Kai / Shiki.** OGs translates them: Hiryu Custom, F-32V Schwert Custom, Grungust Type 0, Grungust Type 3. Akurasu romanizes: Hiryuu Kai, Schwert Kai, Grungust Reishiki, Grungust Sanshiki.
- **Spirit commands.** OGs uses the Valor / Flash / Persist / Wall / Bullseye / Pierce / Gain / Spirit / Vigor / Mettle / Hope set (confirmed from its spirit description table). Akurasu's 2nd OG spirit page uses Hotblood / Fortitude / Iron Wall / Sure-Hit / Direct Hit / Great Effort / Yell / Guts / Fighting Spirit / Expectation. Akurasu's own 2nd OG pilot pages mix both sets.
- **Inside the OGs patch itself:** both "Alchemie" (358 lines) and "Alfimi" (76) appear as speaker names, and both "Kota" (315) and "Kouta" (22).

## Pilots (13)

| Japanese | OGs patch (uses) | Akurasu 2nd OG | Pick |
|---|---|---|---|
| リューネ | Lüne (898) | Ryuune | |
| シュウ | Shu (528) | Shuu | |
| キョウスケ | Kyosuke (3539) | Kyousuke | |
| リュウセイ | Ryusei (3227) | Ryuusei | |
| ユン | Eun (535) | Yun | |
| ラトゥーニ | Latune (1749) | Latooni | |
| ゼンガー | Sänger (1621) | Sanger | |
| レーツェル | Rätsel (667) | Ratsel | |
| リシュウ | Rishu (382) | Rishuu | |
| デスピニス | Despinis (13) | Despenes | |
| コウタ | Kota (496) | Kouta | |
| ショウコ | Shoko (204) | Shouko | |
| アルフィミィ | Alchemie (449) | Alfimi | |

## Units (7)

| Japanese | OGs patch (uses) | Akurasu 2nd OG | Pick |
|---|---|---|---|
| グルンガスト零式 | Grungust Type 0 (32) | Grungust Reishiki | |
| グルンガスト参式 | Grungust Type 3 (23) | Grungust Sanshiki | |
| ビルトビルガー | Wildwürger (9) | Wildwurger | |
| フェアリオン・タイプＧ | Fairlion Type G (2) | Fairlion Type-G | |
| Ｆ‐３２Ｖシュヴェールト改 | F-32V Schwert Custom (3) | F-32V Schwert Kai | |
| ヒリュウ改 | Hiryu Custom (519) | Hiryuu Kai | |
| ダイゼンガー | Dygenguar (27) | DyGenGuar | |

## Weapons and attacks (11)

| Japanese | OGs patch (uses) | Akurasu 2nd OG | Pick |
|---|---|---|---|
| Ｇ・リボルヴァー | G-Revolver (8) | G. Revolver | |
| Ｇ・レールガン | G-Railgun (3) | G. Railgun | |
| Ｍ９５０マシンガン | M950 Machine Gun (6) | M950 Machinegun | |
| ガンレイピア | Gunrapier (3) | Gun Rapier | |
| シシオウブレード | Shishioh Blade (95) | Shishiou Blade | |
| リープ・スラッシャー | Leap Slasher (76) | Reap Slasher | |
| ロシュセイバー | Roche Saber (2) | Rochesaber | |
| スピリットテイカー＋ | Spirit Taker (2) | Spirit Taker + | |
| マインドブラスト | Mindblast (2) | Mind Blast | |
| 修理装置 | Repair Module (5) | Repair Device | |
| 補給装置 | Resupply Module (5) | Resupply Device | |

## Spirit commands (14)

| Japanese | OGs patch (uses) | Akurasu 2nd OG | Pick |
|---|---|---|---|
| 必中 | Bullseye (19) | Sure-Hit | |
| 直感 | Sense (4) | Instinct | |
| かく乱 | Disrupt (5) | Confusion | |
| 加速 | Accel (6) | Accel (Accelerate) | |
| 同調 | Sync (3) | Alignment | |
| 熱血 | Valor (16) | Hotblood | |
| 闘志 | Mettle (5) | Fighting Spirit | |
| 努力 | Gain (14) | Great Effort | |
| 直撃 | Pierce (51) | Direct Hit | |
| 鉄壁 | Wall (10) | Iron Wall | |
| 不屈 | Persist (5) | Fortitude | |
| 根性 | Vigor (3) | Guts | |
| 気合 | Spirit (29) | Yell | |
| 期待 | Hope (47) | Expectation | |
| ド根性 | Guts (spirit table) | Super Guts | |

## Pilot skills (5)

| Japanese | OGs patch (uses) | Akurasu 2nd OG | Pick |
|---|---|---|---|
| 念動力 | Telekinesis (12) | Telekinetic Power (Nendou) | |
| インファイト | In-Fighter (11) | In Fight | |
| ガンファイト | Gunfighter (4) | Gun Fight | |
| 集中力 | Concentrate (21) | Mental (Focus) | |
| 気力＋（撃破） | Will+ (Kill) (3) | Will+ (Destroyed) | |

## Open question for the 785 names not in the OGs patch

These follow Akurasu or the earlier proposals. Akurasu writes long vowels (Ryuune style). For consistency with the OGs basis, should new names also drop the long "u" and keep umlauts? Answer once; `tools/names_signoff.py` can apply it in bulk.

To decide a row: write OGs or Akurasu in the Pick column (or your own spelling). I will apply the picks to `glossary/signoff.tsv` and rebuild.
