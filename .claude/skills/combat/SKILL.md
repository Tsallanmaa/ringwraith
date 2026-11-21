---
name: combat
description: Run personal combat for the hero using The One Ring rules (stances, attacks, piercing blows, wounds), with adversaries played by the solo rules. Use when the hero fights alone or duels an Archfoe; for the hero leading a Band against a group use /battle.
---

# Combat (hero)

**Load:** `lore/procedures/combat.md` (with its Strider section), `lore/procedures/adversaries.md`, and the foe's
`lore/atoms/adversaries/<slug>.md`.

**The Fight panel:** open it with `fight` (`start`) as soon as the fight begins, `update` it after every round
(Endurance, Hate, Wounded, Weary, fled or slain, advantages, a one-line log), and `end` it with the outcome. It
keeps the numbers; don't repeat them in the chat. Reveal Parry, Armour and Might with `known` once the hero would
know them (after fighting a while, a telling roll, or a kind they have fought before), and add a Fell Ability to
`abilities` the first time a foe uses it. Call `set_scene` with mood `battle` when the fight breaks out.

0. **Is this fight right for the story?** In **story** encounters (the default; see "Fights: keep the tale going"
   in your instructions): size the foes to the hero, show the danger before it strikes, and give the
   hero a chance to avoid, parley or prepare. With easy mode on, a lone hero's fights are gentler still (see
   "Easy mode" in your instructions).
1. **Opening.** Check for surprise or an ambush, and decide whether there is an opening volley. Describe the
   foes, and create an adversary note if a foe matters (`note_new`, kind `adversary`). The player chooses a
   stance; offer one line on each sensible option.
2. **Each round:**
   - **Hero attack:** TN = the hero's STRENGTH TN (`get_tn`) + the foe's Parry. `request_roll` with the
     proficiency. Stance modifiers apply.
     - A hit costs the foe Endurance equal to the weapon's Damage.
     - On a Feat die of 10 or {gandalf}: Piercing Blow. Roll the foe's Protection (`roll_adversary`, its armour
       against the weapon's Injury).
     - Each {success} buys a special damage option, and the player chooses it.
   - **Foe attack:** `roll_adversary` with its rating against the hero's Parry.
     - Foes use Heavy Blow with their {success}.
     - They use Fell Abilities when that gives a clear advantage, spending Hate or Resolve.
     - On a Piercing Blow, the hero rolls Protection (`request_roll`, armour dice against the Injury,
       `chained: true`). A failure means a Wound: `roll_table` `wound-severity`.
3. **Update the sheet immediately:** Endurance, Wounded, Hope (`note_set`).
4. **Morale and ways out.**
   - Story mode: foes break when their leader falls, half are down, or Hate/Resolve hits 0.
   - Once the hero is Weary or Wounded, say out of character that fleeing is an option, and how it would go.
5. **Ending.** Foes at 0 Endurance or Weary may flee or surrender, depending on Hate or Resolve. The hero may flee too.
   - Story mode: a hero who would die is instead captured, left for dead or robbed, unless they knowingly
     took a Foolish risk or the player chooses death. Afterwards, apply Shadow from Dread or Misdeeds if any, and
     update fates in the notes.

**Afterwards:** once the hero has fought a foe (or studied it closely), copy its stat block into the adversary's
note: `ringwraith obsidian statblock --note "<Adversary>" --atom <lore slug>`. Only for foes the hero has met.

**Duel within a Battle:** 3 rounds of this procedure per Clash (see `/battle`).
