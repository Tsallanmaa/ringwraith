---
name: distill
description: Build Ringwraith's library (lore/) from the player's own PDFs - the rules, tables, atoms, rules card, index and maps the table reads during play. Use when setting up Ringwraith, or when adding a book.
disable-model-invocation: true
---

# Distil the books into lore/

Ringwraith plays from `lore/`, a library distilled from the player's own PDFs. This skill builds it. It is a
setup task for Claude Code in this repository, never for the table (the table can't write outside the
campaign vault).

The work is long: run it phase by phase, over several sessions if needed. Progress lives in
`lore/DISTILL.md`, so any session can pick up where the last stopped.

## Ground rules

- **The contract is [docs/lore-format.md](../../../docs/lore-format.md)**, with
  [docs/lore-adventures.md](../../../docs/lore-adventures.md) for places, people and adventures. Read both
  before writing anything, and follow them exactly: layout, frontmatter, table schema, citations, readings.
- **Faithful.** Compress, but never drop a rule, number or exception. Never invent rules. Where the book is
  silent or unclear, write a marked *reading* (lore-format.md#readings). Never mix homebrew into book rules.
- **Everything stays local.** `lore/` and `build/` are gitignored. Never copy book text into a tracked
  file (code, skills, docs). Run `ringwraith guard` on any tracked file you change.
- **What the table needs** is listed in [targets.md](targets.md): the files the play skills and the
  Loremaster's contract open by path, the tables they roll by id, and the map formats.
- **Keep the context small.** Read one section of `build/raw/<book>/` at a time. Give each procedure,
  group of atoms or book chapter to a subagent with: the raw section files, lore-format.md, the target path,
  and what neighbouring files already exist. Review what comes back against the source before going on.
- **Check tables by eye.** Extracted text loses table layout. Render the page
  (`ringwraith render <book> <pdf-pages>`), view the PNG, and only then set `verified: true`.

## Phase 0: start or resume

1. `ringwraith doctor`: the four rules books (`core`, `strider`, `moria`, `screen`) must be recognised. If one
   isn't, help the player name it in `ringwraith.toml` (`[sources]`).
2. If `build/raw/core/` is missing, run `ringwraith extract --phase 1`. For other books the player owns:
   `ringwraith extract <id> ...`, or `--phase 7` for all of them. A PDF with no text layer needs `--ocr`
   (`pip install -e ".[ocr]"` first).
3. Each book's sections are listed in `build/raw/<id>/_index.json` (file, title, pdf pages).
4. If `lore/DISTILL.md` exists, read it and continue from the first open item. Otherwise create it: the
   phases below as a checklist, one line per file or table, ticked as each is written and checked.
5. `ringwraith lore-check` lists every path the table needs that doesn't exist yet. Use it as the to-do list.

## Phase 1: procedures (the rules)

One file per procedure in `lore/procedures/`, from the Core Rules, Strider Mode and the Moria solo chapter.
The list is in targets.md. Each file starts with **Steps**, then a `## Strider Mode` section with the solo
rules, then the group-play detail (lore-format.md#layout). Each one repeats the few facts it needs and links
the rest by path.

Then the Band procedures in `lore/procedures/band/` from Moria, as written, with their Moria context kept,
and `lore/campaigns/moria/` (the underground journeys and the rest of Moria's campaign material).

## Phase 2: tables

Every rollable or look-up table in those books goes in `lore/tables/<id>.yaml`. The ids the table's skills
roll by name are in targets.md and must use exactly those ids. Name every other table in the procedure that
uses it, so the Loremaster knows when to roll it. Check each against the page image, then mark it
`verified: true`. `ringwraith lore-check` validates the schema.

## Phase 3: atoms from the rules books

One entity per file in `lore/atoms/<kind>/` (lore-format.md#atoms): cultures, callings, virtues, rewards,
shadow paths, adversaries (with their `statblock`), patrons, and the places, landmarks, people and items
the rules books describe. Places and people keep **Player-facing** and **Loremaster-only** apart, and a
short **Colour** section.

## Phase 4: the rules card, `lore/core.md`

Written last of the rules, because it summarises them. It is loaded into every turn at the table, so keep it
under about 4,500 tokens. It is a card, not a copy: the essentials for solo play, each section pointing to
its procedure (`## Combat (one hero) [procedures/combat.md]`). Sections:

- a short preamble: the dice icons `{gandalf}`, `{eye}`, `{success}`, and "open the procedure when a ruling
  matters";
- **Tools (the table's):** hero, Ally and Band tests go through `request_roll`, foes through
  `roll_adversary`; yes/no questions through `ask` with a chance (certain, likely, middling, doubtful,
  unthinkable); lore tables through `roll_table` (ids in `INDEX.md`), never invented; TNs through `get_tn`;
- **Tests:** TN 20 − Attribute in a Band campaign; a lone hero (Strider Mode) 18 − Attribute with the
  Strider feature, as easy mode gives a Band hero. Always `get_tn`. Story encounters: see the table's
  contract (`tools/ringwraith/web/prompt.md`, Fights), not repeated here;
- Conditions, Adversaries, Combat (one hero), Council, Journeys (and the Band's), Shadow and the Eye,
  Fellowship Phase, Solo oracles, Band Mode (hero and Allies), Running the game.

## Phase 5: the index, `lore/INDEX.md`

The Loremaster opens it to find what to load. On top, by hand: a **When to load what** table (situation →
files), covering every procedure and campaign file and the atom folders. Below it, the generated lists:
run `ringwraith lore-index`.

## Phase 6: Band Mode outside Moria (homebrew, optional)

Only for players who lead a Band outside Moria (`ringwraith new --mode band`, the default). A lone hero
(`--mode strider`) doesn't need it. Moria's Band rules are written for Balin's expedition; `lore/band-mode.md`
adapts them to any region. It is homebrew, so it starts with `status: DRAFT (awaiting user review)`,
`homebrew: true` and `based_on:` the band procedures.

Give each change a bold name: the skills look them up by name. Use these names, for the player's region:
**Patron**, **Safe Haven**, **Pushing back the Shadow**, **Allies**, **Missions** (with the mission grades),
**Hunt threshold**, **Revelation episodes**, **Journeys above ground**, **Battlefields**, **Fellowship Phase**
(with the region's interruption table), **End of the campaign**; then the rulings where the books are silent,
including **"Half the Band"** (in the Readiness bonus). Story encounters and easy mode are not part of it: they
are the table's own rules, in `tools/ringwraith/web/prompt.md`. The homebrew tables it needs (targets.md) carry
`homebrew: true` and a `rationale:`. Go through the draft with the player before play.

## Phase 7: maps (optional)

Without maps, Ringwraith still draws its own region maps as the tale goes, but Eriador has no overview map
and journeys there aren't counted in hexes. With the player's map PDFs (`map-eriador-player`,
`map-eriador-lm`), build the files in targets.md#maps:

1. Find the map image: open the PDF with PyMuPDF and take the largest image's `xref`
   (`page.get_images(full=True)`). Save it to `build/maps/eriador.png`.
2. **Places** (`lore/maps/eriador.yaml`): crop the full-size image a part at a time with Pillow, view the crops,
   and write down the pixel position of each named town, landmark and region, about 25-40 of them.
3. **Hexes** (`lore/maps/eriador-hexes.json`): the Loremaster map has the same geometry with a hex grid. Measure
   the hex width and height in pixels and the centre of one hex as the origin, then classify every hex by its
   land type: `border`, `wild`, `dark`, `impassable` or `sea`. Set `miles_per_px` in eriador.yaml to 20
   divided by the hex width.
4. **Roads** (`lore/maps/eriador-roads.yaml`): each road as a list of stops, each a place name from
   eriador.yaml or an `[x, y]` point along its line.

Check: `ringwraith map journey "<place>" "<place>"` counts hexes and land types along a known road.

## Phase 8: more books (optional)

For each other book the player owns, per its chapters: places, people and landmarks as atoms (an atom that
already exists gets a `## From <book>` block, with the secret split kept); the book's campaign material in
`lore/campaigns/<book>/`; published adventures in `lore/adventures/<book>/NN-*.md`, read by section; and its
tables. Add each to INDEX.md's table, then run `ringwraith lore-index`.

## Finish

1. `ringwraith lore-check -v`: no errors, no broken paths, every table verified and named somewhere.
2. `ringwraith lore-check --readings`: go through the readings with the player, and the Band Mode draft if
   there is one.
3. Tell the player the library is ready: `ringwraith new <name>`, then `ringwraith serve`.
