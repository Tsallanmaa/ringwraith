---
name: session-zero
description: Start a new One Ring campaign with Ringwraith - create the campaign vault, interview the player for the Compass, build the hero (and Band), choose Patron and Safe Haven, and set the opening scene. Use when the player wants to begin a new campaign or there is no active campaign.
---

# Session zero

Session zero is a conversation, not a form. Ask a few questions at a time, offer examples, and let the player
decide. Keep it warm and brisk.

## 1. Campaign
1. The table always runs on one campaign (`ringwraith status` names it). If that campaign is fresh (no hero
   sheet yet), set it up here and go on to step 2.
2. For a different, new campaign: agree on a slug and name and run
   `.venv/Scripts/ringwraith new <slug> --name "<Name>" [--mode band|strider] [--start bree] [--year 2965] [--easy]`
   (defaults: Band mode, Eriador, Bree, 2965). Then tell the player to restart the table (stop `ringwraith serve`
   and start it again), which opens the new campaign, and to type `/session-zero` there. End your turn: anything
   written before the restart would go to the old campaign.
3. Ask about **easy mode** (in a Band campaign: hero TN 18 − Attribute, Band TN 18 − Readiness, plus the Strider
   feature; a lone hero has those by the book, so for them it means gentler fights), **fights**
   (story, the default: sized to keep the tale going; or standard: by the book) and **dice** (scripted, or
   physical dice entered in the tray). Set them with `ringwraith easy on|off`,
   `ringwraith settings difficulty.encounters story|standard` and `ringwraith dice-mode auto|manual`.
4. Ask how much the player wants to steer:
   - **Oracles:** do you read them (you suggest a reading, the player accepts it or gives their own), or does the
     player want to read every answer themselves? Default: you read them.
     `ringwraith settings play.oracle loremaster|player`.
   - **Path cards:** a few ways forward as cards at decision points, or none, so the player comes up with every
     choice? Default: shown. `/paths` shows them on request either way. `ringwraith settings play.paths true|false`.
   - Tell them about `/steer` (point the tale somewhere: "/steer toward Angmar") and that all of these can be
     changed later in the table's Settings.
5. Tell the player to open the vault folder in Obsidian ("Open folder as vault"), and give them the path.

## 2. The Compass
Interview the player, then write `10 Campaign/Compass.md` in their words. Begin with the **premise**: is there
a frame they already have in mind, beyond a backstory and the wishes below? For example, playing through a
published adventure or campaign they own (find it in `lore/INDEX.md`; keep its secrets from them), a specific
story ("we hunt the wight that killed my brother"), or a place and time to stay in. Write it under
`## Premise`, or leave the section empty for a tale that grows from play. Then:
- the tale they want;
- what their hero seeks;
- themes and moods;
- places they'd like to see;
- lines and veils;
- how the tale might end.

Then set `surprise` (low, medium or high) and `pacing` in its frontmatter. Ask whether they'd like **cutaways**
(`cutaways: on`: now and then a short scene elsewhere that the hero doesn't see, like a film) or only what the
hero knows (`off`, the default). Read `lore/procedures/campaign-framing.md`
first, so you can offer era-appropriate ideas for 2965 Eriador.

## 3. The hero
Follow `lore/procedures/character-creation.md` step by step, using the **Band Mode** column for band campaigns and
**Strider** for lone ones.
1. Present the culture and calling options briefly from `lore/atoms/cultures/` and `lore/atoms/callings/`.
2. For attributes, either let the player choose or `roll_table` `chargen-attributes-<culture>`.
3. Create the sheet with `note_new` (kind `hero`), then fill every frontmatter field with `note_set`.
   - The sheet doesn't store TNs: they come from `get_tn`.
   - A Strider campaign, or easy mode, adds the Strider distinctive feature.
4. Write the Appearance, Background and Hopes and Fears sections together with the player.
5. Set a fixed `look:` line, then `queue_art` a portrait for the hero's note.

## 4. The Band (band mode)
Skip this part for a lone hero. Read `lore/procedures/band/band.md`, and outside Moria `lore/band-mode.md`.
1. Agree the Shared Calling (or a personal Calling, which gives the hero a "different path").
2. Recruit **six Allies** (or fewer if the player wants; the Band rules apply unchanged), and let the player choose them:
   - Prepare a few more candidates than places. For each:
     - `roll_table` `band-gifts-eriador` (`band-gifts` for Dwarves) and `band-quirks-eriador`;
     - take a name from the culture's list in `lore/atoms/cultures/<culture>.md`;
     - write one line on who they are.
   - The player picks. They can rename, re-roll or choose anything they dislike, or describe someone of their own.
   - Create nothing until the player has chosen.
3. Create the notes with `note_new` (kind `ally`, fields gift, quirk, culture, look), and `queue_art` each portrait.
4. Fill in `20 Fellowship/Band.md`: Shared Calling and roster list.

## 5. Patron, Safe Haven, situation
1. Choose a **Patron** (`lore/atoms/patrons/`) and record it on the hero sheet.
2. The **Safe Haven**: by the Core Rules (`lore/procedures/fellowship-phase.md`) for a lone hero; for a Band,
   by `lore/band-mode.md` (Safe Haven) outside Moria. Bree and the Prancing Pony by default. Create place notes for it as soon as they
   matter, and queue scenery for Bree.
3. Set up 1–2 hidden **fronts** in `.ringwraith/fronts.md`.
   - Draw them from `lore/atoms/places/` Loremaster-only sections, `lore/atoms/landmarks/` and the Compass.
   - Record any published material you put in play in `.ringwraith/secrets.md`.
4. Fill in `.ringwraith/state.md`: phase adventuring, date and season, location, land type, Eye Awareness
   (`eye-awareness-base`, plus `eye-awareness-band` for a Band), and Hunt threshold.
5. **Maps:** put the tale on the map before it starts.
   - **On the Eriador map** (the Shire, Bree-land, the Lone-lands, Rivendell, Tharbad…): the base maps already hold
     the land. If the starting place isn't on them yet, add it with `place`. If the start is somewhere without a
     close map (anything but Bree-land), draw one round it with `region_map`.
   - **Beyond the Eriador map** (Dunland, Rohan, Wilderland, Lórien…): first draw a **land map** with `region_map`
     (`parent: none`, `scale: land`): a few hundred miles of the country, true to Tolkien's maps, with its places,
     roads, rivers, forests, mountains, and `land`/`lands` marked for journeys. Then a region map of the starting
     area inside it if play will be local.
   - Put the company where the tale begins with `move`.
   - Set `region_land` in the state to the land type around the Safe Haven.

## 6. Opening
1. Create `Session 001` with `note_new` (kind `session`, a title).
2. Call `set_scene` for the opening, then open the first scene with a short, vivid description of where the hero
   is, and ask what they do. Offer Paths only if they ask or hesitate.
