---
name: session-end
description: Close a One Ring play session - write the session note, update sheets, threads, timeline and hidden state, award experience and queue art. Use when the player says they want to stop, pause, or end the session.
---

# End a session

Find a natural pause first: finish the current exchange, but don't force a cliffhanger resolution. Stopping in
the middle of a fight, council, journey or Fellowship Phase is fine (step 6). If a roll is waiting, settle it first:
a roll request doesn't survive the break, so one left waiting has to be asked again next session.

1. **Session note** (the current `Session NNN.md`):
   - **Whereabouts first:** everyone's whereabouts (in `<table-state>`, or `show_map`) should match the fiction.
     Record any missing moves with `move` before the next step.
   - **The record and the road:** run `.venv/Scripts/ringwraith chronicle`. It writes **As it was played** into
     the note from the table log (every scene with its painting, the full narration, the player's moves,
     portraits, rolls and oracle answers) and draws **The road**: the session's travels in ink on the map, with
     the legs and links to the map notes in `60 Maps/`. Run it again if more is played before the note is final;
     it replaces its own sections. Report what its output says, not what an earlier session end said.
   - **The tale:** the session retold as one continuous story, in story voice, past tense, from the hero's point of view.
     - Write it from the chronicle (`ringwraith chronicle --print`), not from memory.
     - Cover every scene; no scene is skipped or reduced to a line. Keep the best dialogue.
     - Embed each scene's painting where its scene begins: `![[90 Assets/scenes/<file>.png]]`, using the paths from the chronicle.
     - Embed the portrait of each newly met person when they first appear: `![[90 Assets/portraits/<file>.png|220]]`.
     - No rules or numbers in the tale; the record and the Rolls list carry those.
   - **Frontmatter:** set `in_game_date` (year and season) and `tale_days`: the first and last tale day the session covered, e.g. `"5-11"`. The calendar places the session from it.
   - **People met** and **Places:** wiki-links.
   - **Gains and losses:** treasure, gear, wounds, Allies lost.
   - **Rolls:** a compact list of the notable rolls from `.ringwraith/rolls.log` since the session began.
2. **Experience:**
   - By default, 3 Skill and 3 Adventure points, or milestones if the campaign uses them (`experience-milestones-*` tables).
   - Add the points to the hero's `xp` with `note_set` and record them in the session frontmatter.
3. **Sheets:** check that the hero, Band and Ally frontmatter matches the fiction (Endurance, Hope, Shadow, Fatigue, conditions, injuries, Gifts wasted, gear).
4. **Notes:** make sure every new NPC, place, item and adversary that matters has a note.
   - **Consistency sweep:** go through the chronicle for every change of fate or fact: who was lost, found, hurt,
     healed, captured, freed, joined or left; which foes were slain or fled; what changed hands; what was learned.
     For each, check that the notes agree: the frontmatter (Ally `status`/`injury`, adversary `fate`, NPC status), the
     Deeds or "What the hero has seen" sections, Threads, Timeline and fronts. Fix every mismatch. A note that says "fate
     unknown" after the story has told the fate is a bug.
   - **Encounters:** every named person the hero dealt with this session has a line for it
     (`ringwraith note encounter "<Name>" "<what happened>" --day <tale day>`), in story order, oldest first.
     Someone met in several scenes gets a line per scene that mattered.
5. **Threads:** add new open threads and move resolved ones to Resolved. Add dated events to `Timeline.md`.
6. **Hidden state:**
   - update `.ringwraith/state.md` (scene line, location, date, Eye Awareness, Hunt threshold, pending consequences);
   - **tidy the state's body.** It is what the next session's fresh conversation remembers the campaign by, so
     it must stay short and whole. Keep four sections and nothing else:
     - `## The story so far`: the whole campaign in at most about 500 words, rewritten (not appended to) each
       session: who the hero is now, what has happened and why it matters, who stands where, promises and
       debts. Recent events in more detail, older ones in a line or two;
     - `## Current scene`: where the tale stopped, in a few sentences;
     - `## Pending consequences`: what is set to happen, and when;
     - `## Notes to self`: secrets of play that fit nowhere else (how you mean to play someone, a reveal held back).

     Fold the scene-by-scene notes made during play into these and delete them: the session note keeps the
     full record. If the file has no `The story so far` yet, write it now from the session notes' tales.
   - the `scene` line describes the current moment in one or two sentences. Don't let it accumulate history ("PREVIOUSLY…"): that belongs in the session note;
   - check the deadlines and counters: close any that were met or missed, or that the story made moot, with
     `deadline` / `counter`. Note in one OOC line what you closed and why;
   - advance fronts in `fronts.md` and update `secrets.md` with anything revealed;
   - **stopping part-way through something:** a fight, council, journey or Fellowship Phase still under way stays
     open (don't `end` it); its tool keeps the state, and the next session picks it up with `show`. Name it in
     the `scene` line. Anything offered but not yet chosen (recruit candidates, a council's terms, a choice of
     undertakings) goes into the `scene` line too, in short, so the next session offers the same, not new ones.
7. **Art:** queue anything iconic from this session that has no image yet (one scene image is a good default) with
   `queue_art`. Every image made this session should appear in the session note (the chronicle and the tale embed them).
8. **Obsidian:** run `ringwraith obsidian sync` (puts sessions, journeys and missions on the Shire Reckoning
   calendar from their tale days), then `ringwraith obsidian home` (rewrites the Home dashboard, with this
   session's road map).
9. Say goodbye in a line of story voice. Then give one out-of-character line: what's pending, and roughly how much XP was earned.
