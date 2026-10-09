# Choices for Anthony

Decisions only you can make, newest at the bottom of each section. Write your
answer under each item (or just "OK" to accept the suggestion). Name-by-name
picks between the OGs patch and Akurasu live in `deviations.md`; this file
holds everything else.

Status key: **open** (needs you), **suggested** (I picked a default; say if you
disagree), **done**.

## Names and terms

1. **OGs vs Akurasu picks**: open. 50 rows in `deviations.md` (Pick column).
   Until you pick, builds use the OGs form.
2. **Style for the 785 names the OGs patch never uses**: open. Akurasu writes
   long vowels (Ryuune, Kouta); OGs drops them (Lune, Kota) and keeps umlauts.
   Suggested: follow OGs style for consistency (short vowels, umlauts where the
   German original has them). One answer covers all 785.
3. **The ü glyph**: open. The game font has ä but no ü, so "Lüne" and
   "Wildwürger" can't display as-is. Options: (a) I draw a ü into the font from
   the existing u and ä glyphs; (b) plain "Lune" / "Wildwurger". Suggested: (a).
4. **206 uncertain name proposals**: open. Rows in `glossary/signoff.tsv` whose
   notes end in "?" (mostly Chokijin and Shan Hai Jing enemy attacks, Gan Eden
   and Li-Technologist attack names, a few minor Masou Kishin pilots and units).
   Mark the `signed` column "y" when a row is right, or fix the `en`.
5. **鋼龍戦隊 (the player's fleet)**: open. Not in the OGs script. The pilot
   used "Steel Dragons" (from the glossary). Alternatives: "Steel Dragon
   Squadron", "Kouryu Squadron". Suggested: "Steel Dragon Squadron" in full,
   "Steel Dragons" for short when width is tight.
6. **Pilot-scene terms** (prologue, first use in the game): open, suggested as
   the pilot wrote them:

   | Japanese | Pilot's English | Note |
   |---|---|---|
   | ガイアセイバーズ / セイバー | Gaia Savers / "Savior" | Suggested fix: "Saver", to match Gaia Savers |
   | イデアラント | Idealants | |
   | シェード | the Shade | |
   | サテライト・シーカー | Satellite Seeker | |
   | ファウ・ケルン | Fau Kern | |
   | オヅヌ博士 | Dr. Ozunu | |
   | 可視領域 | field of view | |
   | ＧＳ | GS | kept as the abbreviation of Gaia Savers |

## UI wording forced by space

7. **実戦 stage label** (64 px box): suggested "Live". "Live Fire" does not fit.
8. **非表示** ("hidden", toggle label): suggested "Off". "Hidden" is 3 px too
   wide.
9. **Long generic speaker names** such as ルザック州軍兵士Ａ ("Luzak State Army
   Soldier A", 412 px): suggested short forms ("Luzak Soldier A") for name boxes
   once I've measured the name-box width.

## Style

10. **Honorifics**: done. None, except "Rishu-sensei" (from the OGs patch).
11. **Quote marks**: done. None on spoken lines; thoughts in parentheses (OGs).
12. **Ranks**: done. Written in full ("Lieutenant", never "Lt."), as in OGs.
13. **Spirit command names**: covered in `deviations.md` (OGs: Valor, Wall,
    Bullseye, Pierce, Gain, Spirit... vs Akurasu: Hotblood, Iron Wall,
    Sure-Hit, Direct Hit, Great Effort, Yell...). Suggested: OGs set.

## Translation pass

14. **Model**: suggested Claude Opus 5.5 for story and battle quotes (quality
    matters most), estimated $40-$100 for the whole game via the Batch API.
    Claude Sonnet 5.5 would be about half that. Say if you'd rather use Sonnet
    for menus and data tables, or for everything.
15. **Spend cap**: open. I'll run one chapter first and report its exact cost
    before the full run. A monthly limit in the Anthropic console is the hard
    safety net; tell me the number you set so I can stay under it.
