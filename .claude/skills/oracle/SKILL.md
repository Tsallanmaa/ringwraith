---
name: oracle
description: Answer a question about the world using the solo oracles (Telling table for yes/no, Lore tables for open questions, Fortune/Ill-fortune for dramatic icons). Use when the player asks a question the fiction does not settle, or when Ringwraith genuinely does not know an answer.
---

# Oracle

Use the oracle when the answer is **genuinely unknown**. If the story already makes the answer obvious, just
answer. Details are in `lore/procedures/solo-play.md`.

- **Yes/no:** decide the chance from the fiction (certain, likely, middling, doubtful or unthinkable), then call
  `ask` with the question and the chance.
  - On `{gandalf}` or `{eye}`, the answer is extreme or comes with a twist.
  - In the OOC summary, give the chance you chose and why, in one short clause.
- **Open questions:** `roll_table` with `lore-strider` and a `column` (action, aspect or focus).
  - Roll 1–3 columns. Use `lore-moria` when you want a `feature`, which suits places and rooms.
  - Interpret the words in the light of the scene, the region's lore atoms and Tolkien's world. Offer the
    interpretation, and let the player suggest another.
- **Dramatic icons:** when a hero roll succeeds with `{gandalf}`, or fails with `{eye}`, at a dramatic moment,
  roll `fortune-strider` (or `fortune-moria` in band play) or `ill-fortune`. Apply any Eye Awareness changes the
  result gives.
- **NPC or Ally reactions:** `ask`, with the chance set by their attitude.
- Hidden questions (the answer is for you alone) pass `show_player: false`. Either way, tell what came of it as
  story first; the OOC summary names the oracle.
