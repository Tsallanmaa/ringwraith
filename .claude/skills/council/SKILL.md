---
name: council
description: Run a One Ring council (social encounter) - resistance, introduction, time limit, interaction rolls and outcome. Use when the hero seeks something important from a person or group through words.
---

# Council

**Load:** `lore/procedures/council.md`, plus `lore/procedures/band/band-council.md` for Band play.

**The Council panel:** open it with `council` (`start`) once the request and Resistance are set, before the
introduction roll; `update` it with the time limit the introduction sets (`rounds`), and after every exchange
(`used`, the successes it won as `add`, the listeners' `attitude` if it shifts, a one-line `log`); `end` it with
the outcome. It keeps the count; the player sees only how far the listeners are swayed and the exchanges left,
so don't repeat the numbers in the chat.

1. **Set the request and its Resistance** by how much it asks (the procedure's levels). If unsure between two
   levels, `ask`. Check the NPC's note for motives and attitude.
2. **Introduction.** The hero rolls the fitting skill (Courtesy, Awe, Riddle, etc.) with `request_roll`. This
   sets the time limit, as the procedure says.
3. **Interaction.**
   - Play each exchange out. The player states the hero's argument and you voice the NPC in their own words.
   - Then `request_roll` the skill the argument uses; its successes count against the Resistance as the
     procedure says. The panel keeps the running count.
   - One Ally with a relevant Gift may add (1d).
   - `ask` for specific reactions and the `lore-strider` table for what the NPC brings up.
4. **Outcome.**
   - Resistance reached within the time limit: success, a great one if achieved early.
   - Otherwise: failure, or a partial agreement with a cost.
5. Update the NPC's `attitude` (`note_set`) and add the scene with `ringwraith note encounter`. A council counts
   as a Fellowship milestone in solo play.
