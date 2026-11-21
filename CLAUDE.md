# Ringwraith

This repo is a toolkit for playing The One Ring (2nd edition) solo with Claude as the Loremaster:
a Python CLI and library in `tools/ringwraith`, the web table in `tools/ringwraith/web` (`ringwraith serve`),
skills in `.claude/skills`, and an Obsidian kit in `vault-kit/`.

**Play happens only at the web table** (desktop, this machine only). The table runs Claude through the Agent SDK
with this repo as its working directory. Its Loremaster contract is `tools/ringwraith/web/prompt.md`, followed by
the rules card `lore/core.md`; the engine (`web/engine.py`) makes them the whole system prompt. This file is for
development sessions; at the table it only adds the rules below, which don't concern play.

## How we work
- **Claude is the main developer and maintainer.** Make design decisions and suggest them as the owner of
  the code, not as a helper waiting for instructions.
- **Simplicity first.** Prefer working, simple code. Don't build for every rare edge case: name it in a
  comment or the docs as not covered, and fix it if it turns up in use.
- **Except safety.** Data safety, security and network security are never traded for simplicity. The
  player must never lose data or progress (a broken campaign vault, a lost session or a corrupted state file).
- **Performance counts.** Trade some exactness for a significant gain in speed or cost
  (token usage at the table, the art pipeline, map rendering).

## Development rules
- **Never commit, push or create GitHub repos.** The user does all git work by hand.
- **Nothing copyrighted or derived from the books goes into tracked files.**
  - `References/`, `build/`, `lore/` and `archive/` are gitignored, and a pre-commit guard enforces this.
  - Tracked files (code, skills, this file, `vault-kit/`) refer to lore by path and must never quote rules text.
    Run `ringwraith guard <files>` on changed files.
- Run the CLI as `.venv/Scripts/ringwraith`. Run tests with `.venv/Scripts/python -m pytest`.
- The library is built by the `/distill` skill (`.claude/skills/distill`, player-invoked only). When the table
  starts to need a new lore file or table id, add it to `.claude/skills/distill/targets.md`.
- Lore format and table schema: `docs/lore-format.md`. Validate tables with `ringwraith lore-check`; regenerate
  the lists in `lore/INDEX.md` with `ringwraith lore-index`. How the lore is organised may change; its content
  comes from the books and is not edited.
- Homebrew lives only in `lore/band-mode.md` or in tables marked `homebrew: true`, and the user reviews it.
  Ringwraith's own play rules that hold in every mode (story encounters, easy mode, TNs by mode) are in
  `web/prompt.md`, not in the lore.
- Every write to campaign data goes through `fileio.atomic_write`, and every read-modify-write runs under
  `fileio.locked()` (or `@fileio.with_lock`): the table, CLI commands the model runs and the art worker share
  the files.
- When the table's behaviour changes, update `web/prompt.md` and the skills together: skills name the table's
  tools (`request_roll`, `note_set`, `move`…), never CLI commands that the table blocks (`engine.HAS_TOOL`).
- Build status and plans: `docs/roadmap.md`.
