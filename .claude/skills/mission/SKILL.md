---
name: mission
description: Plan a Band mission - objective, roster of Allies, composition, Readiness, Eye Awareness and Hunt threshold - and record it in a mission note. Use when the hero and Band set out on a new task from their Safe Haven.
---

# Plan a mission

**Load:** `lore/procedures/band/missions.md` and `lore/band-mode.md` (Patron, Missions, Hunt threshold).

1. **Objective.** The story's own goal comes first: a thread, a Patron request, or a hook the player chose. If
   there is none, `roll_table` `mission-objectives-eriador` and shape the result together with the player.
2. **Create the note:** `note_new` (kind `mission`, fields objective, patron as `[[Patron]]`, start_day).
3. **Roster.**
   - The player chooses which Allies go.
   - Allies still suffering conditions carry them into the mission.
   - Count the Hardened Allies and apply the bonus from `readiness-bonus`; "half the Band" means half of those on
     this mission (band-mode.md, "Half the Band").
4. **Composition.**
   - The player picks size, war gear and specialisation (see `band-composition`).
   - Compute the Dispositions (default 2, plus modifiers), the Burden, and the Readiness and its TN.
   - Write all of it to the mission note, and copy the Dispositions and Burden to `Band.md` (`note_set`).
5. **Eye Awareness.** Hero base (`eye-awareness-base`) plus Band size (`eye-awareness-band`) plus Famous items.
   Write it to state.md.
6. **Hunt threshold.** The land type of the region (`hunt-threshold-core`), plus the core modifiers
   (`hunt-modifiers`), plus the previous mission's grade and the Fellowship-phase duration
   (`hunt-threshold-modifiers`; the grades are in band-mode.md, Missions). Write it to state.md.
7. **Set off.** Mark the mission `status: underway`, set `mission:` in state.md, and usually start `/journey`.
8. **When it ends:** set `status`, `grade` and `end_day`, write "What happened", clear `mission:`, then go
   to `/fellowship`.
