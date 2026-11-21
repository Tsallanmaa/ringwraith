---
name: journey
description: Run a One Ring journey - plan the route, marching tests, journey events, the interludes between them, fatigue and arrival, shown on the Journey panel. Use when the hero (and Band) travel through dangerous or wild country.
---

# Journey

Short, safe trips need no journey. Narrate them (with `move`), or make a single TRAVEL roll.

## Load
- Hero with a Band, overland: `lore/band-mode.md` (Journeys above ground), plus `lore/procedures/journey.md`.
- Lone hero: `lore/procedures/journey.md` (the Strider Mode section).
- Underground in Moria: `lore/procedures/band/band-journeys.md`, plus `lore/campaigns/moria/moria-journeys.md`.

## Steps
1. **Plan with the player.**
   - Set the destination, route and waypoints. Add any that aren't on the map with `place`.
   - Call `plan_journey` (from, to, via). It counts the hexes entered (destination counted, departure not) and
     the miles, shows the player the route, and tells you alone the land types in order and the road hexes.
     Never reveal the land types. An event on a road hex: its Skill roll gains (1d); in hard terrain (hills, woods,
     marshes: judge from the map and the region's atom) it loses (1d).
   - Note the season. In state.md set the current land type and Hunt threshold.
   - **Set out:** `journey` (`start`: from, to, via, a title, season, mode). It opens the Journey panel, creates
     the journey note and sets `journey:` in the state. Call `set_scene` for the road.
2. **Marching test.**
   - With a Band, the Band rolls MANOEUVRE vs the Readiness TN (`request_roll`, who `Band`), which sets ±dice on
     the hero's TRAVEL.
   - The hero rolls TRAVEL (`request_roll`, TN from `get_tn`). Easy mode or Strider: the hero is Inspired, per
     the Strider feature.
   - The result decides how many hexes ahead the next event comes. Tell the stretch of road as story, then
     `journey` (`log`, kind `march`, hexes_done).
3. **The road between: interludes.** The days between events are lived, not skipped.
   - **At each night's camp**, and wherever the story calls for one, offer an interlude: a short played-out
     moment with no event roll. Draw it from the Allies (a Quirk showing, a Deed remembered, an open thread, two
     of them at odds), the Compass, the hero's hopes and fears, and the land itself (a ruin on the skyline, an
     old song the place recalls, weather that changes the mood).
   - Make it interactive: give an Ally a few lines and let the player answer, ask, or take the talk elsewhere;
     offer Paths only if they help. Keep it to a scene, not a chapter. "We press on" skips it.
   - Record it with `journey` (`log`, kind `interlude`, a title and one line of what passed). It costs no
     fatigue unless the story says so. A rest day is kind `rest`.
4. **Event.**
   - `roll_table` `strider-journey-events`, Favoured in Border Lands and Ill-favoured in Dark Lands. The table
     chains to its detail table.
   - Choose the target: with a Band, roll a Success die (odd = the Band, even = the hero).
   - Tell the event concretely as story, using the region's atom. Then roll the indicated skill, or the
     Disposition from `skill-to-disposition` (an Ally's Gift may help).
   - A Noteworthy Encounter becomes a full scene.
   - Record it with `journey` (`log`, kind `event`, title, at, who, outcome, fatigue_hero, fatigue_band). The
     tool adds the hero's fatigue to the sheet; don't also `note_set` it. The Band takes its Fatigue test and an
     Injury if hurt (Ally notes with `note_set`).
5. **Along the way:** `move` the Company as it reaches each stage, so the map and its "you are here" follow, and
   `advance_time` for the days on the road. Check the Eye after each event: when Eye Awareness reaches the Hunt
   threshold, trigger a Revelation (see `lore/procedures/eye-awareness.md`).
6. **Repeat** marching tests, interludes and events until arrival.
7. **Arrival.**
   - Fatigue is converted as the procedure says.
   - `move` the Company to the destination (this clears the planned route and marks the place as where they are).
   - `journey` (`end`, status `arrived`, a one-line outcome). The tool completes the journey note, clears
     `journey:` in the state and closes the panel. Turning back is status `abandoned`.
   - Call `set_scene` for the arrival, and queue scenery of the destination if it has none.
