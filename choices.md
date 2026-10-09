# Choices for Anthony

Decisions only you can make, newest at the bottom of each section. Write your
answer under each item (or just "OK" to accept the suggestion). Name-by-name
picks between the OGs patch and Akurasu live in `deviations.md`; this file
holds everything else.

Status key: **open** (needs you), **suggested** (I picked a default; say if you
disagree), **done**.

## Names and terms

1. **OGs vs Akurasu picks**: open. 50 rows in `deviations.md` (Pick column).
   Until you pick, builds use the OGs form. Approved 2026-10-09: translate now
   with defaults; your picks get swapped in afterwards across all worksheets.
2. **Style for the 785 names the OGs patch never uses**: open. Akurasu writes
   long vowels (Ryuune, Kouta); OGs drops them (Lune, Kota) and keeps umlauts.
   Suggested: follow OGs style for consistency (short vowels, umlauts where the
   German original has them). One answer covers all 785.
3. **The ü glyph**: done (approved 2026-10-09: add ü to the font). The game font has ä but no ü, so "Lüne" and
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

14. **Model**: done (approved 2026-10-09: Opus 5.5 for everything). Was: suggested Claude Opus 5.5 for story and battle quotes (quality
    matters most), estimated $40-$100 for the whole game via the Batch API.
    Claude Sonnet 5.5 would be about half that. Say if you'd rather use Sonnet
    for menus and data tables, or for everything.
15. **Spend cap**: done (approved 2026-10-09: full pass tonight, stop at $75 total
    including retries). Was: open. I'll run one chapter first and report its exact cost
    before the full run. A monthly limit in the Anthropic console is the hard
    safety net; tell me the number you set so I can stay under it.

## Found while testing the full English build (2026-10-09)

16. **Menu wording**: suggested. The map command menu reads Move / Attack /
    Ground / Spirit / Stats. 着地 came out "Ground" (as in "ground the unit");
    "Land" is the more usual SRW term. 能力 came out "Stats". Say if you want
    either changed; one-word fixes are free (no API needed).
17. **Text inside pictures**: open. The title menu (START / LOAD / CONTINUE /
    LIBRARY, already English), the legal notice screen and some logos are
    images, not text. Translating the legal notice means editing a texture.
    Suggested: leave it Japanese for now, revisit at release.
18. **Short stage-script words kept Japanese**: open until tested. Words like
    ゲームオーバー, 非表示 and 移動 in the stage scripts repeat like script
    labels, so I left them Japanese to avoid breaking stages. If you ever see
    Japanese text on screen during a stage (e.g. "Game Over"), tell me where.
19. **Playtest areas I could not reach by script**: battle screen and battle
    quotes, intermission menus, library pages (I assumed they scroll and let
    English run 1.6x the Japanese line count), save/load screens.
