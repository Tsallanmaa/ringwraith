---
name: npc
description: Bring a new named character into the story - name, look, motive, attitude, note and portrait. Use when a new NPC becomes important or the player asks who someone is.
---

# New NPC

1. **Canon first.** Search `lore/atoms/npcs/` and the place atoms for an existing character who fits (Grep for the
   name or role in `lore/atoms`). Use canon characters as written, and reveal only what the hero would know.
2. **Otherwise invent one:**
   - **name:** from the culture's list in `lore/atoms/cultures/<culture>.md`;
   - **nature:** `roll_table` `lore-strider`, column `aspect`;
   - **want:** column `focus`;
   - one memorable detail, and a fixed `look:` line.
3. **Create the note:** `note_new` (kind `npc`) with fields culture, role, location (`[[Place]]`), attitude,
   look, first_met (the session). Write only player-known facts into the body. Keep secret motives in
   `.ringwraith/secrets.md` or `fronts.md`.
4. **Portrait:** `queue_art` (preset `portrait`, the `look:`, the note).
5. **Voice:** give them a distinct way of speaking from their first line.
