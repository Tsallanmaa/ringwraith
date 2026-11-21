---
name: art
description: Queue or regenerate illustrations (portraits, scenery, items, adversaries, scenes) for the campaign vault via the local Lemonade image server. Use when the player asks for a picture, or about the art settings.
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
- **Regenerate:** queue the same note again; the new picture replaces the old one under the title.
- **Settings** (Bash, `.venv/Scripts/ringwraith settings …`):
  - model: `settings art.model Flux-2-Klein-4B` (the worker picks it up on its next start);
  - on or off: `settings art.enabled false`;
  - style: `settings art.style book|classic`.
- **Pending:** `ringwraith art pending`.
