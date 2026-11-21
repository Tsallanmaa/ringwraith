# Developing Ringwraith

The [README](../README.md) is for players. This page is for working on Ringwraith itself. The rules for
development sessions with Claude Code (what may be committed, how campaign files are written) are in
[CLAUDE.md](../CLAUDE.md). Build status and plans are in [roadmap.md](roadmap.md).

## Setup

```sh
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"      # bin/ instead of Scripts/ on Linux and macOS
cp ringwraith.example.toml ringwraith.toml           # adjust the paths
cp docs/claude-settings.example.json .claude/settings.json   # optional: your vaults path
git config core.hooksPath .githooks                  # enable the copyright guard
```

The pre-commit guard blocks `References/`, `build/`, `lore/` and `archive/`, PDFs, text
copied from a PDF and files over 1.5 MB. Run it by hand on changed files with `ringwraith guard <files>`.

## Tests

```sh
.venv/Scripts/python -m pytest
```

Tests use synthetic data only.

## Project layout

```
tools/ringwraith/          The library and CLI: dice, tables, vault, clock, art queue, chronicle
tools/ringwraith/geo/      Maps, places, whereabouts, travels and journey routes
tools/ringwraith/web/      The table: FastAPI server, the Agent SDK engine, its tools and panels,
                           the Loremaster contract (prompt.md) and the browser page (static/)
tools/ringwraith/extract/  Reading the PDFs: text, dice icons, runes
.claude/skills/            The Loremaster's procedures: journeys, combat, battles, councils, sessions…
vault-kit/                 The campaign vault: skeleton, note templates and the Obsidian theme
docs/                      Lore format, roadmap, art models, the README's images and the demo session
scripts/                   Retaking the screenshots
tests/                     pytest, synthetic data only
```

At the table, the engine (`web/engine.py`) runs Claude through the Agent SDK with this repository as its
working directory. The system prompt is `web/prompt.md` followed by the rules card `lore/core.md`.

## The books and the library

### Recognising the PDFs

`tools/ringwraith/sources.py` lists the known books by id (`core`, `strider`, `moria`, `screen`, …) with
the words their file names must contain, so any sensible name works . A name that fits no book, or two equally well, is reported by `ringwraith doctor`. A player can
then name the file in `ringwraith.toml`:

```toml
[sources]
core = "My rulebook.pdf"
```

Files the lore refers to by name (a map's `source: {pdf: ...}`) are found through `sources.resolve()`,
which falls back to the reader's own copy of the same book.

### Extraction

```sh
ringwraith extract --phase 1          # Core Rules, Strider Mode, Moria, the screen -> build/raw/
ringwraith extract ruins rivendell    # by source id
ringwraith extract <id> --ocr        # a PDF with no text layer (pip install -e ".[ocr]")
ringwraith render moria 211-213       # page images, for checking tables and layouts by eye
```

- Dice icons are vector drawings in the PDFs. The extractor restores them as `{gandalf}`, `{eye}` and
  `{success}` tokens. Unrecognised drawings next to text become `{icon?}`.
- Running headers and footers are removed. Page markers (`<!-- page N -->`) are kept, so distilled notes
  can cite their source.
- Tables come out as cell soup, so distillation checks them against rendered pages.

### Distillation

`lore/` is distilled from `build/raw/` with Claude Code, by the `/distill` skill
([.claude/skills/distill](../.claude/skills/distill/SKILL.md)). The skill only runs when the player types it;
the Loremaster at the table never sees it. Its [targets.md](../.claude/skills/distill/targets.md) lists what
the table needs from the library (the paths the play skills open, the table ids they roll, the map formats).
`ringwraith lore-check` reads it too, so a missing target shows up as a broken path. When the table starts
to need a new lore file or table id, add it there. The format, layout and table schema are in
[lore-format.md](lore-format.md), with the adventure and colour guidelines in
[lore-adventures.md](lore-adventures.md). How the lore is organised may change; what it says comes from the
books and is not edited.

```sh
ringwraith lore-check -v              # validate lore/ against lore-format.md
ringwraith lore-index                 # regenerate the lists in lore/INDEX.md
```

## Dice and tables from the command line

The same rolls the table makes, for testing. They aren't written to the campaign's roll log, so they never reach
a session record:

```sh
ringwraith roll 3 --tn 14 --favoured --hope        # Feat die + 3 Success dice (+1 for Hope)
ringwraith roll 2 --tn 15 --feat 8 --success 4 6   # evaluate physical dice
ringwraith odds 3 --tn 14                          # the chance of success, with and without Hope
ringwraith ask likely                              # the Telling table
ringwraith table                                   # list the distilled tables
ringwraith table lore --times 2                    # roll one
```

## Art

Image models, speeds and the portrait-reference pipeline are in [art-models.md](art-models.md).
`ringwraith art models` lists what Lemonade offers, and `ringwraith art test` paints the same prompts with
each model for comparison.

## Screenshots

The README's screenshots are taken from a staged session at the real table, so they can be retaken after
any UI change:

```sh
.venv/Scripts/python scripts/screenshots.py [name ...]     # retake all, or the named ones
.venv/Scripts/python scripts/screenshots.py --art [key ...] # repaint the demo's art (needs Lemonade)
```

The demo session, *The Long Dark*, is [screenshots/session.py](screenshots/session.py): chapters of what
the player typed, what Ringwraith told and what its tools did, and `SHOTS`, which says where each shot
stops and what is clicked before it. For each shot, the script builds a fresh campaign in a scratch folder
(never in your vaults), plays the chapters with the table's own library calls, starts the table with
Claude switched off and photographs it at 1920×1200 with headless Chrome. The shots are saved as JPEG in
`docs/images/`.

To change a shot, edit its chapter or its entry in `SHOTS`. The paintings are in `screenshots/art/`; their
prompts and seeds are in `ART`. The region maps are copied from a local campaign that has them
(`--regions-from`, by default `lorien-test`). The Eriador map comes from the books and is never shown.

To see the demo with your own style LoRA, paint and shoot it into a gitignored folder:

```sh
.venv/Scripts/python scripts/screenshots.py --art --into build/shots-lora --looks-from <campaign> --look hall=<look> ...
.venv/Scripts/python scripts/screenshots.py --into build/shots-lora
```

`--looks-from` takes the campaign's `art.lora`, and each `--look` gives one painting a look; a sketch takes the
campaign's `sketch` look by itself. The script refuses to paint with a LoRA into `docs/`: the repository's
pictures stay in the house style.
