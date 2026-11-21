---
name: art
description: Queue or regenerate illustrations (portraits, scenery, items, adversaries, scenes, sketches) for the campaign vault via the local Lemonade image server. Use when the player asks for a picture, or about the art settings.
---

# Art

The table runs the art worker itself; never start one.

- **Queue:** `queue_art` with a preset (`portrait`, `scenery`, `adversary`, `item`, `scene`), the subject, and the
  note to attach it to.
  - The subject is the note's `look:`, plus pose or setting. Name up to 3 characters in `characters` so their
    portraits keep faces the same.
  - A portrait, scenery, adversary or item picture becomes the note's own picture (`image:`) and replaces the one
    under its title. A scene painting is only added to the note.
- **Scene changes** paint themselves through `set_scene`; don't queue them as well.
- **Sketches:** `sketch` draws a small pencil drawing into the tale of something told or heard but not seen.
  It isn't attached to a note.
- **Looks:** if the campaign has a style LoRA, its looks are listed under "Painting looks" in your instructions;
  pass one as `look` to `set_scene` or `queue_art`. A look paints without portrait references.
- **Regenerate:** queue the same note again; the new picture replaces the old one under the title.
- **Settings** (Bash, `.venv/Scripts/ringwraith settings …`):
  - model: `settings art.model Flux-2-Klein-4B` (the worker picks it up on its next start);
  - on or off: `settings art.enabled false`;
  - style: `settings art.style book|classic`;
  - a style LoRA and its looks: `art.lora`, set up by the player in the campaign's settings file (see
    `docs/art-models.md`). Don't change it yourself.
- **Pending:** `ringwraith art pending`.
