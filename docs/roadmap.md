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
  paintings, live hero and Band sheets, Fight and Journey panels, cutaways, the Tale drawer and roll log.
- **Maps:** Eriador with hexes and roads, region and land maps drawn on demand, site plans, the travel log
  with a timeline, journey plans, session maps.
- **Art:** local paintings through Lemonade in the books' style, with consistent faces from portrait
  references.
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
- **The table:** a Shadow (dark) theme, sound; move the frontend to Svelte if
  it grows.
- **Art:** a style LoRA, only if prompts look too generic; paper grain or a
  vignette baked into the images.
