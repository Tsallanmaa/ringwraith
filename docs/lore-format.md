# Lore format

`lore/` is Ringwraith's library. It is distilled locally from the reference PDFs and is **never
committed** (see `.gitignore` and the pre-commit guard). This document is the contract for what goes
in it, so that distilled files from different sessions or agents fit together and `ringwraith roll`
can read the tables.

## Purpose and reader

The reader is **Claude acting as Loremaster** mid-game. Files must be:

- **Operational.** Procedures as numbered steps, exact numbers (TNs, dice, costs, thresholds), and
  every edge case the rules state. Cut flavour text, examples and designer commentary unless an
  example settles an ambiguity; if so, compress it to one line.
- **Faithful in voice.** Rules are compressed, but places, people, landmarks and adventures keep a short
  **Colour** section: sensory details, history, how people speak, proper names, brief in-world quotes
  (verse, inscriptions, rumours). Ringwraith narrates from these, so the tale must stay true to Tolkien.
  Details are in `docs/lore-adventures.md#colour-keeping-it-tolkien`.
- **Dense, not lossy.** Paraphrase in plain English, but never drop a rule, modifier or exception.
  If the books contradict each other, keep both and say which one applies in solo play.
- **Cited.** Every section ends with, or carries inline, a source like `[core p.112]`. Use the
  printed page number when the extraction shows one (`<!-- page 116 (printed 112) -->` means
  printed 112), otherwise `pdf` pages: `[moria pdf 224]`. Book ids: `core`, `strider`, `moria`,
  `screen`, `lonelands`, `ruins`, `rivendell`, `realms`, `ss1-*`, `ss2-*`.

Dice icons are written as `{gandalf}`, `{eye}` and `{success}` everywhere.

## Layout

```
lore/
  INDEX.md                  what exists and when to load it: a hand-written guide on top, generated lists
                            below (`ringwraith lore-index`)
  core.md                   Tier 0: always loaded (after the table's contract). At most about 4,500 tokens.
  procedures/               Tier 1: one file per game procedure (rules only), loaded when it starts
  procedures/band/          official Moria Band rules (as written, Moria context kept)
  campaigns/<book>/         a book's campaign, setting and subsystem material (`campaigns/moria/moria-journeys.md`,
                            `campaigns/ruins/ruins-campaign.md`); file names keep the book prefix, so they stay unique
  band-mode.md              HOMEBREW generalisation of Band rules to any region (user-reviewed)
  adventures/<book>/NN-*.md published adventures (Loremaster-only), read by section
  tables/<id>.yaml          rollable tables (schema below)
  atoms/<kind>/<slug>.md    Tier 2: one entity per file (culture, calling, virtue, reward,
                            adversary, place, patron, landmark, item...)
  maps/                     base maps, the Eriador hex grid and roads (traced from the official map)
```

Procedure files start with a **"Steps"** list. **The solo rules (a `## Strider Mode` section) come right after
the Steps**, before the group-play detail, so a solo game can stop reading there. Each file is self-contained:
it repeats the two or three facts it needs from elsewhere and links others by path
(`see procedures/combat.md#wounds`). Paths are relative to `lore/`; `ringwraith lore-check` fails on any that
point nowhere.

### Readings

Where the books are silent or unclear, the distiller may add a ruling of their own: a **reading**. It is never
mixed silently into the book's rules. Mark it in one of these forms, and use no other:

- `(reading)` right after the sentence it qualifies;
- `(reading: why)` or `(reading, from …)` when the reason or source matters;
- a line or list item that starts `Reading:` for a longer one.

`ringwraith lore-check --readings` lists every reading for the user to review, like homebrew. Once the user
approves one, its line says so (`(reading, approved by the user <date>: …)`), and it is no longer listed.

### Atoms

One entity per file, with YAML frontmatter:

```yaml
---
kind: adversary            # culture | calling | virtue | reward | adversary | place | patron | landmark | item | npc | shadow-path ...
name: Marsh Ghoul             # an invented example
aliases: []
tags: [undead, marsh]
source: [core p.123]
secrets: false             # true if the note contains Loremaster-only knowledge (most places/NPCs do)
---
```

Then the body. Adversaries keep their full stat block in a fenced `statblock` YAML block:

```statblock
name: Marsh Ghoul         # invented numbers: the real ones come from the book
attribute_level: 4
endurance: 14
might: 1
hate: 3          # or resolve: N
parry: 1
armour: 2
proficiencies:
  - {name: Claws, rating: 2, damage: 3, injury: 14, special: [Seize]}
fell_abilities:
  - {name: Cold Grip, text: "..."}
```

Places carry a `region:` field and, if known, `hex:` or a description of where they lie, plus
**Player-facing** and **Loremaster-only** sections, kept separate so Ringwraith can reveal the first
without the second.

An atom marked `secrets: true` always has a Loremaster-only part (a heading, or a bold line such as
`**Loremaster-only additions**`). When a second book extends an atom, its `## From <book>` block keeps the
same split; a block without one starts with `**Loremaster-only** (added from this book; …)`, because hiding too
much only costs a detail, while revealing too much spoils a secret. `ringwraith lore-check -v` warns about atoms
that don't follow this.

## Table schema

```yaml
id: lore                     # = file name, kebab-case, unique across lore/tables
title: Lore Table
source: [strider p.18, moria p.208]
use: "Open-ended questions. Roll on one column for a word, or several for a phrase."
dice: [feat, success]        # rolled in this order; each die indexes one level of `entries`
columns: [action, aspect, focus, feature]   # optional: leaves are mappings with these keys
favoured_ok: true            # optional: may this table be rolled Favoured / Ill-favoured
entries:
  gandalf:                   # feat keys: 1..10, gandalf, eye, or ranges like "1-3"
    1: {action: <word>, aspect: <word>, focus: <word>, feature: <word>}
    2: ...
  eye:
    1: ...
  1:                         # success keys: 1..6 or ranges "1-2"
    1: ...
notes: "Anything a roller must know that is not in the entries."
```

- Allowed dice: `feat` (1–10, `eye`, `gandalf`), `success` (1–6), `feat-number` (the number on the
  feat die, where icons are separate rows), `d6`, `d12`.
- Keys are integers, the strings `eye` and `gandalf`, or range strings `"a-b"` (inclusive). Every
  possible roll must hit exactly one key.
- Leaves are a string, or a mapping. For a mapping, `text` is the main result. Other fields are
  structured effects, e.g. `{text: Despair, skill: AWARENESS, fatigue: 2, consequence: "..."}`.
- Leaves can point to another table with `then: <table-id>` for a follow-up roll.

Threshold tables, such as the Telling table, use `kind: threshold`:

```yaml
id: telling
kind: threshold
dice: [feat]
chances: {certain: N, likely: N, middling: N, doubtful: N, unthinkable: N}   # the Feat die needed for yes
default: middling
yes: "Yes"
no: "No"
gandalf: "Yes, with an extreme result or twist"
eye: "No, with an extreme result or twist"
```

Static reference tables (weapons, armour, war party stats...) that are looked up, not rolled, use
`kind: reference` with a `rows:` list of mappings.

Every table should be named somewhere a Loremaster will see it (a procedure, an atom, a skill, or a `then:`
chain); `ringwraith lore-check -v` lists tables that nothing names.

**Verification.** Every table must be checked against the rendered page (`ringwraith render <book>
<pdf-pages>`, then view the PNG), because extracted text loses table layout. Rows keyed by
`{gandalf}`/`{eye}` are the easiest to get wrong. Put `verified: true` in the table once you have
checked it against the page image.

## Homebrew

Anything not in the books is homebrew. It lives in `band-mode.md`, or in tables or atoms with
`homebrew: true` and a `rationale:`. It is never mixed silently into official rules. (Ringwraith's own play
rules for every mode, such as story encounters and easy mode, are in `tools/ringwraith/web/prompt.md`.) The user reviews
homebrew before it is used in play.
