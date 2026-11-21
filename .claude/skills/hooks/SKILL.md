---
name: hooks
description: Find adventure seeds and side paths that fit the hero's region, season, Compass and Patron - from the published adventures' hooks, landmark rumours, lore atoms, patron quests and Tolkien lore. Use when the player wants ideas for what to do next, a new mission, or a side quest.
---

# Hooks and side paths

1. **Where and when:** state.md gives the location, season and land type. Read `lore/procedures/campaign-framing.md` for the era.
2. **Gather seeds** (read only what you need):
   - `lore/atoms/places/` for the current region and its neighbours: Loremaster-only sections, adventure seeds, rumours;
   - `lore/atoms/npcs/` linked to those places, and their motives;
   - `lore/atoms/landmarks/`: their **Rumour** sections are player-facing hooks;
   - **published adventures** (`lore/INDEX.md` → Adventures):
     - pick those whose frontmatter `region`, `when` and `hooks` (patron, place, previous adventure) fit the hero's situation;
     - read **only the Hook section** at this stage. Their premise and structure are secrets, and you open them only once the player takes the hook;
     - respect the book's order where adventures build on each other (e.g. the Lone-lands series, the Starter Set's five);
   - the books' campaign files with plot seeds (`lore/campaigns/<book>/`): `campaigns/ruins/ruins-campaign.md` (the Dark Designs timeline), `campaigns/moria/moria-campaign.md`, `campaigns/ss1/ss1-shire.md`;
   - Patron quests: `roll_table` `patron-quests-<patron>`;
   - Band missions: `roll_table` `mission-objectives-eriador`;
   - the fronts in `.ringwraith/fronts.md`: a hook that touches a front is stronger;
   - general Tolkien lore that fits 2965 and the region, with no anachronisms.
3. **Shape 3–5 hooks.** Each has:
   - a one-line rumour or request, as the hero would hear it;
   - who brings it;
   - why it fits the Compass;
   - rough risk and distance.

   Keep Loremaster secrets out of the hook text.
4. Let the player pick, combine or ignore them. Record the chosen hook as a thread in `Threads.md`.
5. If they take a published adventure's hook:
   - note it in `.ringwraith/secrets.md` (book, adventure, the part you are in);
   - read the adventure file in full before the next scene;
   - run it through the player's choices, not as a script. Adapt it to the hero, the Band and the Compass, using the file's Solo and Band notes;
   - draw on its **Colour** sections and its people's and places' atoms, so the narration keeps the book's voice.
