---
name: paths
description: Offer the player 2-4 concrete directions for their hero (Paths) tied to the Compass, open threads and the current scene. Use when the player asks what they could do, seems stuck, or types /paths.
---

# Paths

1. Look at:
   - the current scene (state.md);
   - `10 Campaign/Compass.md`;
   - `10 Campaign/Threads.md`;
   - the hero's hopes, fears and Patron;
   - any active mission or journey.
2. Choose **2–4 Paths**. Each is one short line, concrete and actionable now ("Ask the old Ranger at the Pony what
   he saw at the Forsaken Inn"), serving a Compass theme, a thread, an Ally or the Patron.
3. Aim for **variety**: at least one that follows the main thread, one that serves a Compass wish or an Ally's
   personal goal, and one side path or wildcard. For side paths, use `/hooks` thinking: the region's atoms and
   patron quests.
4. Ask the closing question, then call `offer_paths` with them. (With Path cards off, `play.paths: false`, offer
   them only when the player typed `/paths`.) The cards add "something else" themselves.
5. Don't choose for the player, and don't hint which Path is "right". If they pick one, play it out.
