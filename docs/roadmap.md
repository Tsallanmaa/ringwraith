# Ringwraith roadmap

## Where we are: Ringwraith 0.9

Playable end to end, solo, at the web table (`ringwraith serve`), with the Obsidian vault as the tale's
archive.

- **Setup:** PDFs recognised by name (`doctor`), extraction with dice icons, and the `/distill` skill that
  builds the library (`lore/`) from them, checked by `lore-check`.
- **Rules:** the Core Rules, Strider Mode and the Moria solo and Band rules, with tables as YAML. Band Mode
  outside Moria is homebrew in `lore/band-mode.md`. Story encounters, easy mode and the TNs for each mode are
  in the Loremaster's contract (`web/prompt.md`).
- **Lore:** every book in the manifest distilled: places, people, adversaries, landmarks, adventures and
  campaigns, with Colour sections and `/hooks` across them.
- **The table:** streamed narration, the dice tray (odds, Hope, physical dice), Paths, oracles, scene
  paintings, live hero and Band sheets with short tooltips on what each number does, cutaways, the Tale
  drawer and roll log.
- **Procedure panels:** Fight (combat and Band battles, with what each advantage and complication gives),
  Council, Journey and Fellowship. Each keeps its state in `.ringwraith/` and shows the player only what the
  hero can tell; the page draws them from that saved state, never from how far back the event log reaches.
- **Session safety:** play can stop anywhere. An open fight, council, journey or Fellowship Phase stays open
  across sessions: Ringwraith is told it is under way and reads it back with `show`. After a reboot or closed
  tab the conversation resumes, a session that was never ended carries on in the same session note, and the
  chronicle keeps it as one session. State files are written atomically and the table log is flushed to disk
  on every event. Only a reply cut off mid-stream or a roll left waiting has to be asked again.
- **Token use:** Begin session starts a fresh conversation after a session that was ended; the campaign is
  remembered by the vault (a bounded story-so-far in the hidden state, rewritten at each session end). The
  model is set per campaign with `table.model`, from the table's Settings dialog (with the dice, easy mode,
  encounters and paintings) or the CLI.
- **Steering:** the player chooses how much of the tale comes from their own imagination and how much from
  Ringwraith's. They can read the oracles themselves (Ringwraith suggests a reading; the player accepts it or
  says what the answer means instead) and turn the Path cards off to come up with every choice unprompted
  (`/paths` still asks for them). Both are in the Settings dialog, and session zero asks about them. `/steer`
  points the tale somewhere ("toward Angmar"), and Ringwraith brings it round through the world. The Compass
  holds a premise, such as a published adventure to play through, and the steers.
- **Maps:** Eriador with hexes and roads, region and land maps drawn on demand, site plans, the travel log
  with a timeline, journey plans, session maps.
- **Art:** local paintings through Lemonade in the books' style, with consistent faces from portrait
  references. Pencil sketches in the tale of what is told but not seen. Optional looks from your own style
  LoRA (`art.lora`), chosen by Ringwraith scene by scene.
- **Vault:** session chronicles, Home as a logbook, the Shire Reckoning calendar, stat blocks, Bases indexes,
  the Parchment and Shadow theme.
- **Development:** tests on synthetic data, the copyright guard, repeatable README screenshots
  (`scripts/screenshots.py`).

## To do

- **Play-test a lone hero (Strider Mode).** Every campaign so far has been a Band campaign. Run a short one:
  session zero, a journey leg, a fight and a Fellowship Phase.
- **Run `/distill` from scratch** on a clean checkout, to find what a new player hits. The Eriador map
  calibration (phase 7) is the likeliest to need help.

## Ideas

- **Chases** (deferred).
- **Maps:** Hunt-modifier and hard-terrain hexes in journey counting; a Bree town map; an interactive Leaflet
  block in the Obsidian map notes.
- **Easy mode:** more options if play proves too harsh.
- **The table:** a Shadow (dark) theme; move the frontend to Svelte if
  it grows.
- **Art:** paper grain or a vignette baked into the images; picking a look from the Settings dialog; looks
  with portrait references (needs a LoRA for the reference model).
