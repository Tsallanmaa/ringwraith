---
name: fellowship
description: Run a Fellowship Phase at the Safe Haven - duration, recovery, interruptions, undertakings, experience spending, Hardened Allies and recruiting. Use when the hero returns to safety after an adventure or mission.
---

# Fellowship Phase

Check the campaign's mode (`campaign.mode` in the settings). Steps marked **Band** are for `band` campaigns
only; a lone hero (`strider`) skips them.

**Load:**
- Band: `lore/procedures/band/band-fellowship.md`, and outside Moria `lore/band-mode.md` (Safe Haven,
  Fellowship Phase).
- Always: `lore/procedures/fellowship-phase.md` and `lore/procedures/advancement.md`.

1. **Duration.** The player chooses Hurried, Brief or Extended; Yule counts as Extended, with the Yule benefits.
   Set `phase: fellowship` in state.md.
2. **Recovery.**
   - Hope, Endurance and Wounds by duration.
   - **Band:** Ally injuries, fatigue and wasted Gifts by duration.
   - Shadow: remove 1–3 depending on the deeds (spiritual recovery for the solo player).
   - Update all the sheets with `note_set`.
3. **Updates.**
   - Spend Skill and Adventure points (`experience-points-costs`; max +1 rank per Skill and Proficiency, and
     VALOUR *or* WISDOM). A new VALOUR rank brings a Reward; a new WISDOM rank brings a Virtue.
   - **Band:** award **Hardened** status to one Ally who earned it, with an optional title.
   - Give Kingly Gifts if any were won.
4. **Band: interruption** (Brief or Extended).
   - Roll a bare Feat die: `request_roll` with 0 dice (who the hero, what "Fellowship interruption"), Ill-favoured
     if the phase is Extended.
   - On an {eye}, `roll_table` `fellowship-interruption` in Moria, or the region's table from band-mode.md
     outside it (`fellowship-interruption-eriador`), and play out the scene briefly. The player loses
     one undertaking.
5. **Undertakings** (0, 1 or 2 by duration). Choose from `undertakings`. **Band:** also Recruit Allies and
   Establish a Safe Haven (band-mode.md, Safe Haven).
   - **Band: Recruit Allies. The player chooses who joins.** Don't pick the recruits yourself.
     1. **How many.** Work out the number by the rule (`lore/procedures/band/band-fellowship.md`) and say it. The
        player may take fewer, never more. If the player names a number, that number stands.
     2. **What kind of folk.** Use the player's stated wish ("folk who can stand witness"). If they gave none, ask
        in one line.
     3. **Candidates.** Prepare two more candidates than there are places (at least three). For each:
        - `roll_table` `band-gifts-eriador` and `band-quirks-eriador`;
        - choose a culture that fits the Safe Haven, and a name from `lore/atoms/cultures/<culture>.md`;
        - write one line on who they are and why they'd join.

        Present them as a short numbered list (name, culture, Gift, Quirk, that line). Write nothing to the vault yet.
     4. **The player picks.** They may also rename someone, re-roll or choose a Gift or Quirk they dislike, or
        describe someone of their own (then roll or agree the Gift and Quirk with them).
     5. **Only then** create the notes (`note_new`, kind `ally`), update `20 Fellowship/Band.md`, `queue_art` the
        portraits, and bring the newcomers into the story.
   - Meet Patron is a good time to give the next mission.
6. **Close.**
   - Advance fronts for the time that passed, and `advance_time` the days.
   - Update the date and season in state.md and Timeline.md.
   - Set `phase: adventuring` when it's over.
