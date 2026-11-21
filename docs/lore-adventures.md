# Adventure format (lore/adventures/)

Published adventures are distilled into `lore/adventures/<book>/<NN>-<slug>.md`, one file per
adventure. They are **Loremaster-only**: Ringwraith keeps their secrets and runs them only if the
story leads there (the player chooses Paths; `/hooks` can offer an adventure's hook). Like all of
`lore/`, these files are local and never committed.

```yaml
---
kind: adventure
name: The Drowned Barrow           # an invented example
book: lonelands
number: 2
source: [lonelands p.40-58]
region: [lone-lands, weather-hills]   # region slugs, as used by atoms/places
when: "2965 or later; autumn"          # the year/season the book suggests, and any prerequisites
length: "3-4 sessions"
tags: [ruins, undead]
hooks: [patron:<id>, place:<id>] # how it can be reached: patrons, places, other adventures
secrets: true
---
```

Sections, in this order:

1. **Hook (player-facing)**: what the hero could hear or be asked: a rumour, a request, a job. No
   secrets. 2–5 lines Ringwraith can read out or paraphrase.
2. **Premise (Loremaster)**: what is really going on, who wants what, the twist. Short.
3. **Cast**: each named NPC in one or two lines, with a link to their atom when one exists
   (`atoms/npcs/<slug>.md`). Create atoms for recurring or important NPCs.
4. **Structure**: the parts or episodes in order, as numbered steps. For each:
   - where it happens (link `atoms/places/<slug>.md`);
   - what the heroes find or face;
   - the rolls the book calls for: skill, TN or Resistance, and what success, great success and
     failure lead to;
   - the branches.

   Keep every number and condition; cut descriptive prose to what the Loremaster needs to narrate.
5. **Adversaries**: links to `atoms/adversaries/<slug>.md`, with numbers per encounter. Create
   atoms with full stat blocks for any new adversary.
6. **Rewards and consequences**: treasure (link items), experience notes, Shadow, Eye Awareness,
   what changes in the world.
7. **Solo and Band play**: how to run it with one hero (Strider Mode) or a hero and Band (see
   `band-mode.md`). Include the book's own guidance, and say plainly where you are adapting.
8. **Threads**: loose ends, follow-ups, and links to later adventures.

End every section with its citation, e.g. `[lonelands p.101]`.

## Colour: keeping it Tolkien

Rules are distilled tightly, but **the world's voice is not cut**: Ringwraith narrates from these files,
and the tale should sound like Middle-earth. Every adventure, and every place, NPC and landmark atom, has
a short **Colour** section (5–12 bullets):
- concrete sensory details: what you see, hear and smell there, the weather, the light;
- the history and legend behind it, in a sentence each;
- how people speak: turns of phrase, sayings, oaths, the way an NPC addresses strangers;
- names in their proper forms (Sindarin, Westron, Dwarvish, Hobbit), with meanings when the book gives them;
- in-world texts that carry the voice, quoted briefly: a rhyme, a verse, an inscription, a rumour as
  folk tell it. Keep quotes to a few lines; these files are local and never committed.

Never invent lore in a distillation; mark any reading of your own as `(reading)`.
