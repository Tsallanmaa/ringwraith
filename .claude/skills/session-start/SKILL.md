---
name: session-start
description: Begin or resume a play session of the active One Ring campaign - load state, recap and pick up the scene. Use when the player says they want to play, continue, or resume.
---

# Start a session

1. Run `.venv/Scripts/ringwraith status`. If there is no active campaign, offer `/session-zero`.
2. **Read**, in this order:
   - `.ringwraith/state.md` (scene, day and time, deadlines, Eye Awareness, Hunt threshold, active mission or journey);
   - **review the deadlines and counters** against the story so far. For each one, ask: is the hero still racing
     against it? If the story has settled what it was for (met or missed, the threat exposed or cancelled), close
     it with `deadline` (action `done`) and say so in one OOC line in the recap. If it's unclear whether it still
     matters, ask the player rather than guess;
   - the last session note;
   - `10 Campaign/Compass.md` and `10 Campaign/Threads.md`;
   - the hero sheet and `20 Fellowship/Band.md`;
   - `.ringwraith/fronts.md` and `.ringwraith/secrets.md`.

   Open lore procedure files only when they're needed.
3. Create the new session note with `note_new` (kind `session`, a working title). It sets `session` in the state.
4. **Where everyone is:** the `<table-state>` line lists the map's whereabouts. If they don't match the story (a
   move that was never recorded), fix them with `move` before the recap.
5. **Recap** ("Previously…") in 3–5 sentences of story voice. Call `set_scene` for where the tale stands.
6. **Fronts.** If in-game time passed since last session, advance fronts as needed (`ask`: "Does <front>
   advance?", likely if ignored). Note any new grim portent to weave in.
7. Resume the scene where it stopped, and ask the player what they do.
