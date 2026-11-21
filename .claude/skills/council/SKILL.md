---
name: council
description: Run a One Ring council (social encounter) - resistance, introduction, time limit, interaction rolls and outcome. Use when the hero seeks something important from a person or group through words.
---

# Council

**Load:** `lore/procedures/council.md`, plus `lore/procedures/band/band-council.md` for Band play.

1. **Set the request and its Resistance** by how much it asks (the procedure's levels). If unsure between two
   levels, `ask`. Check the NPC's note for motives and attitude.
2. **Introduction.** The hero rolls the fitting skill (Courtesy, Awe, Riddle, etc.) with `request_roll`. This
   sets the time limit, as the procedure says.
3. **Interaction.**
   - Play each exchange out. The player states the hero's argument and you voice the NPC in their own words.
   - Then `request_roll` the skill the argument uses; its successes count against the Resistance as the
     procedure says. Keep the running count in a one-line OOC note.
   - One Ally with a relevant Gift may add (1d).
   - `ask` for specific reactions and the `lore-strider` table for what the NPC brings up.
4. **Outcome.**
   - Resistance reached within the time limit: success, a great one if achieved early.
   - Otherwise: failure, or a partial agreement with a cost.
5. Update the NPC's `attitude` (`note_set`) and add the scene with `ringwraith note encounter`. A council counts
   as a Fellowship milestone in solo play.
