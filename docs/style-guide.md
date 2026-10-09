# Style guide (draft for Anthony's review)

Sources: engine tests in `docs/rendering.md`, the OGs PS2 fan patch text
(decoded from `ogs.xdelta`), the camd11 OG Gaiden patch as observed in
`glossary/sources.md`, and the glossary. Items marked
**decide** need Anthony's call.

## Hard rules (the engine enforces these; `tools/fitcheck.py` checks them)

- Never type ASCII `<` or `>`. The engine treats `<...>` as a control tag and
  deletes it. Keep existing tags such as `<W=63>　</W>` exactly as they are.
- Keep `%d`, `%s`, `%02d` and other format codes, in the same order.
- Line breaks: `@` in story scripts, stage text and EBOOT messages; `/`
  followed by an ideographic space (U+3000) in battle quotes; a real newline
  in data tables. There is no automatic wrapping.
- Dialogue boxes hold 3 lines. Width budgets (current font metrics): story
  832 px per line, battle quotes 704 px. Menus and help keep the width and
  line count of the Japanese field.
- Strings marked `keep` stay Japanese: `[ＤＭ]-name` speaker keys, `[１]-001`
  event keys, asset paths. The engine matches them byte for byte.
- Half-width ASCII for all English text. No full-width Latin letters or
  digits.

## Names and terms

- Basis: the English of the OGs PS2 fan patch, checked against Akurasu.
  `glossary/signoff.tsv` holds every data-table name with both forms;
  `deviations.md` lists where they disagree for Anthony to decide. The build
  fails on a non-canonical form of a signed-off term.
- Given name first ("Masaki Andoh"). Speaker name boxes use the short form
  the game uses (マサキ becomes "Masaki").
- Units: Title Case, model codes as written (`R-1`, `MP Gespenst Mk-II`).
- Attacks: Title Case, hyphenated prefixes (`T-Link Knuckle`). Translate
  Japanese-word attack names unless the canon keeps the romanization
  (`Shishioh Blade`, `Bakuraifu`).
- Spirit commands: canon names (Valor, Flash, Focus, ...). Where a menu has
  4-letter slots, use the canon abbreviations once the width check shows
  which menus need them.

## Dialogue

- Honorifics: none. Decided from the OGs patch, which has no -san, -kun,
  -chan or -sama in 53,168 dialogue lines. The one exception it keeps is
  "Rishu-sensei"; keep that where the Japanese has it. Ranks are written in
  full ("Captain", "Lieutenant", "Commander"), never "Lt.", plus "sir".
- Japanese quote brackets 「」 and （） become plain English: spoken lines get
  no quotation marks (the name box shows the speaker); inner thoughts stay in
  parentheses. **decide**: the original keeps 「」 on every spoken line; dropping
  them gains two characters of width per line.
- Register: natural, contraction-heavy English. Keep each character's voice:
  Masaki brash, Shu cool and formal, Ryusei excited, Kyosuke terse,
  Excellen playful. Per-character notes grow in this file as the edit pass
  goes on.
- Ellipsis `...` (three periods, cheaper than `…` at current widths), em-dash
  as `--`, exclamation and question marks single unless the Japanese stacks
  them for effect (`!!` allowed, never more).
- Leave gender unspecified where the Japanese does (battle quotes aimed at
  "the enemy pilot").

## UI

- Menu labels in Title Case, status banners in ALL CAPS, stat labels
  abbreviated as in the OGG patch (Mob, Mel, Skl, Rng, Def, Acc, Eva).
- Victory and defeat conditions numbered as in the Japanese ("1. Destroy all
  enemies.").
- Empty slots stay as the Japanese dash runs.

## Battle quotes

- Short and punchy. 26,050 unique lines are reused across pilots, so keep a
  line neutral when the same Japanese serves several speakers.
- The `/` + U+3000 break must survive; at most 3 lines.
