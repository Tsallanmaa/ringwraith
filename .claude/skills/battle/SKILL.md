---
name: battle
description: Run a Band battle (Moria solo Battle rules) - war party, objectives, battlefield, leader focus, stance, Clash rolls, setbacks and duels. Use when the hero and their Band fight a group of foes.
---

# Battle (hero and Band)

**Load:** `lore/procedures/band/battles.md`. Outside Moria, also `lore/band-mode.md` (Battlefields).

**The Fight panel:** open it with `fight` (`start`, kind `battle`) as soon as the battle begins, `update` it after
every Clash (the foe's Resistance and Might, objective, advantages and complications, leader focus, Band stance,
a one-line log), and `end` it with the outcome. It keeps the numbers; don't repeat them in the chat. Reveal what
the hero would know with `known`. Call `set_scene` with mood `battle` when it breaks out.

0. **Story check.** In **story** encounters (the default; see "Fights: keep the tale going" in your instructions),
   a Battle comes from the story, with a chance to avoid it or prepare.
1. **Foes.**
   - Set the war party's scale (`roll_table` `war-party-stats`; Ill-favoured with a large Band, Favoured with a
     small one), which gives its Might and Resistance. Story mode: Favoured, unless the story has clearly gathered
     a large force.
   - Archfoe: `roll_table` `archfoe-modifiers`. If one appears, choose a fitting adversary atom. Story mode: an
     Archfoe appears only where the story has built toward one.
   - Band TN: `get_tn` with Readiness (easy mode lowers it).
   - Before the first Clash, tell the player plainly what the Clash roll is up against and what withdrawing
     would cost; the tray shows the exact odds when the Clash is rolled.
2. **Objective** (if any): give it a Resistance by the procedure.
3. **Battlefield:** `roll_table` `battlefield-aspect-overland` (`battlefield-aspect` underground or in ruins), and
   note the advantages and complications it creates. On the Fight panel give each its `effect` (+1d, −1d),
   `persistent` if it lasts the battle, and a one-line `text` in story terms (the player's tooltip).
4. **Get in position.** The hero rolls BATTLE (`request_roll`, Favoured or Ill-favoured by the situation). This
   gives an advantage or a complication for the first Clash.
5. **Each Clash:**
   - The player picks the **leader focus** (Command, Inspire, Fight or Duel) and the **Band stance** (Aggressive,
     Balanced, Guarded or Fleeing); the `leader-focus` and `band-stances` tables say what each does.
   - Resolve the leader focus roll.
   - **Clash roll:** `request_roll`, who `Band`, WAR (MANOEUVRE if Fleeing) against the TN the procedure sets, with
     the dice that advantages, complications and an Archfoe add or take away. An Ally's Gift can help, at a risk
     to that Ally (the procedure).
   - **Success:** spend the successes (`roll_table` `clash-success` lists the options).
   - **Failure:** the Band makes the procedure's Endurance test (`chained: true`), and persistent
     advantages are lost. **With {eye}:** also `roll_table` `clash-setback`.
   - **Story mode, after a failed Clash:** offer to withdraw: MANOEUVRE +1d, and a failure still gets them
     away at a cost.
   - **Story mode morale:** once the foe's Resistance is at half or less, `ask` (likely) after each successful
     Clash whether they break.
   - **Duel:** Close Quarters rounds as the procedure says, using `/combat`.
6. **End** when the foe's Resistance reaches 0, the foe breaks, the Band escapes, or the Band falls.
   - Story mode: a fallen Band is defeated, not destroyed. Captured, scattered or driven off; Allies who "die"
     are usually *missing*.
   - Update the Ally notes with `note_set`: injury, fatigue, status, wasted Gift.
   - Apply Shadow (Dread) for injuries and Allies lost, as the procedure says.
   - Write the deeds into the Ally notes (`ringwraith note encounter`); they are the basis for making Allies Hardened later.

**Afterwards:** copy the stat blocks of the foes the Band fought into their adversary notes:
`ringwraith obsidian statblock --note "<Adversary>" --atom <lore slug>`.
