# What the table needs from lore/

Paths are relative to `lore/`. `ringwraith lore-check` reports every path below (and every path the play
skills and the Loremaster's contract name) that doesn't exist yet. Ids, file names and folder names are
Ringwraith's own; what goes in the files comes from the books.

## Always

- `core.md`: the rules card, loaded into every turn (SKILL.md, phase 4)
- `INDEX.md`: what to load when (phase 5)

## Procedures

From the Core Rules and Strider Mode:

- `procedures/action-resolution.md`: tests, TNs, Hope, success and its degrees
- `procedures/characteristics.md`: attributes, skills, conditions (Weary, Miserable, Wounded)
- `procedures/character-creation.md`: making a hero (cultures, callings, previous experience, gear)
- `procedures/advancement.md`: experience and how it is spent
- `procedures/combat.md`: personal combat, stances, wounds
- `procedures/adversaries.md`: how foes act; reading a stat block
- `procedures/council.md`: councils
- `procedures/journey.md`: journeys, roles, events, fatigue, arrival
- `procedures/shadow.md`: Shadow, Shadow paths, bouts of madness
- `procedures/eye-awareness.md`: Eye Awareness and the Hunt
- `procedures/fellowship-phase.md`: the Fellowship Phase and undertakings
- `procedures/treasure.md`: treasure and magical rewards
- `procedures/solo-play.md`: the solo oracles
- `procedures/loremastering.md`: running the game, tone, pacing
- `procedures/campaign-framing.md`: Patrons, Safe Havens, the shape of a campaign

From Moria (the Band rules, as written):

- `procedures/band/band.md`: the Band, Allies, Readiness
- `procedures/band/missions.md`
- `procedures/band/battles.md`
- `procedures/band/band-journeys.md`
- `procedures/band/band-council.md`
- `procedures/band/band-fellowship.md`
- `campaigns/moria/moria-journeys.md`: journeys underground

## Atom folders

`atoms/cultures/`, `atoms/callings/`, `atoms/virtues/`, `atoms/rewards/`, `atoms/shadow-paths/`,
`atoms/adversaries/`, `atoms/patrons/`, `atoms/places/`, `atoms/landmarks/`, `atoms/npcs/`, `atoms/items/`.
A culture's file name is the culture in kebab case (`atoms/cultures/men-of-bree.md`), as hero sheets name it.

## Tables the play skills roll by id

Each must exist with exactly this id (`tables/<id>.yaml`).

The oracles:
`tables/telling.yaml` (kind: threshold, with the chances certain, likely, middling, doubtful, unthinkable),
`tables/lore-strider.yaml`, `tables/lore-moria.yaml`, `tables/fortune-strider.yaml`,
`tables/fortune-moria.yaml`, `tables/ill-fortune.yaml`.

Journeys, Shadow and the Eye:
`tables/strider-journey-events.yaml`, `tables/shadow-paths.yaml`, `tables/eye-awareness-base.yaml`,
`tables/eye-awareness-band.yaml`, `tables/hunt-threshold-core.yaml`, `tables/hunt-threshold-modifiers.yaml`,
`tables/hunt-modifiers.yaml`, `tables/wound-severity.yaml`, `tables/experience-points-costs.yaml`,
`tables/archfoe-modifiers.yaml`.

The Band and its battles:
`tables/band-composition.yaml`, `tables/band-gifts.yaml`, `tables/band-stances.yaml`,
`tables/readiness-bonus.yaml`, `tables/leader-focus.yaml`, `tables/battlefield-aspect.yaml`,
`tables/war-party-stats.yaml`, `tables/clash-success.yaml`, `tables/clash-setback.yaml`,
`tables/mission-objectives.yaml`.

The Fellowship Phase, experience and patrons:
`tables/fellowship-interruption.yaml`, `tables/undertakings.yaml`, `tables/skill-special-success-strider.yaml`,
`tables/experience-milestones-strider.yaml`, `tables/experience-milestones-moria.yaml`, and one
`patron-quests-<patron>` table per patron, e.g. `patron-quests-gandalf`.

Hero creation: one `chargen-attributes-<culture>` table per culture (the six attribute rows a culture rolls
on), e.g. `chargen-attributes-men-of-bree`.

## Homebrew tables (Band Mode outside Moria, phase 6)

Only with `band-mode.md`. Each has `homebrew: true` and a `rationale:`. Ids are Ringwraith's own:
`band-gifts-<region>`, `band-quirks-<region>`, `mission-objectives-<region>`,
`fellowship-interruption-<region>` (e.g. `-eriador`), `battlefield-aspect-overland`, and
`skill-to-disposition` (which Band disposition a hero skill stands for).

## Maps

All optional (phase 7). Pixel coordinates are on the full-size map image.

`maps/eriador.yaml`:

```yaml
id: eriador
title: Eriador
source: {pdf: <the player map's file name>, xref: <image xref>}
size: [<width>, <height>]          # pixels
miles_per_px: <20 / hex width>
places:
  <Place name>: [<x>, <y>]
```

`maps/eriador-hexes.json`:

```json
{"grid": {"width": <px>, "height": <px>, "x0": <px>, "y0": <px>,
          "layout": "pointy, odd rows shifted right"},
 "hexes": {"<col>,<row>": "border | wild | dark | impassable | sea"}}
```

`(x0, y0)` is the centre of hex `0,0`; columns and rows may be negative. Hex `col,row` has its centre at
`x0 + col * width (+ width / 2 on odd rows), y0 + row * height`.

`maps/eriador-roads.yaml`:

```yaml
roads:
  <Road name>: [<place from eriador.yaml>, [<x>, <y>], [<x>, <y>], <place>, ...]
```

A region map drawn in miles (`px_per_mile`, `parent`, `anchor`, `bounds`, and lists of places, roads,
woods, hills…) can also live in `maps/`. Ringwraith draws these itself during play
(`.ringwraith/regions/` in the campaign), so none are needed here.
