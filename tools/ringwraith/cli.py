"""`ringwraith` command line."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import time
from pathlib import Path

from . import config as cfg
from . import guard, sources


def _out(msg: str = "") -> None:
    sys.stdout.write(msg + "\n")


# ------------------------------------------------------------------ doctor

def cmd_doctor(args: argparse.Namespace) -> int:
    c = cfg.load()
    ok = True
    _out(f"config      {c.loaded_from}")
    _out(f"references  {c.references} {'ok' if c.references.is_dir() else 'MISSING'}")
    ok &= c.references.is_dir()
    _out(f"build       {c.build}")
    _out(f"lore        {c.lore} {'ok' if c.lore.is_dir() else '(not built yet)'}")
    _out(f"vaults      {c.vaults} {'ok' if c.vaults.is_dir() else '(not created yet)'}")

    if c.references.is_dir():
        found, unknown = sources.scan(c.references)
        missing = [s for s in sources.SOURCES if s.id not in found]
        _out(f"\nsources     {len(found)}/{len(sources.SOURCES)} recognised")
        for s in sources.SOURCES:
            if s.id in found:
                _out(f"  found     {s.id:20} {found[s.id].name}")
        for s in missing:
            _out(f"  missing   {s.id:20} {s.title}")
        for f in unknown:
            fits = [s.id for s in sources.candidates(f)]
            why = (f"fits {' and '.join(fits)}" if fits else "not a known book") if f.suffix.lower() == ".pdf" \
                else "not a PDF; ignored"
            _out(f"  extra     {f.name}  ({why})")
        if missing and any(f.suffix.lower() == ".pdf" for f in unknown):
            _out("  A book you own isn't recognised from its file name? Name it in ringwraith.toml:\n"
                 "  [sources]\n  core = \"My rulebook.pdf\"")

    _out("")
    try:
        with urllib.request.urlopen(f"{c.lemonade_url}/api/v1/models", timeout=3) as r:
            models = [m.get("id") for m in json.load(r).get("data", [])]
        _out(f"lemonade    up at {c.lemonade_url}; {len(models)} model(s) available")
    except Exception as e:  # noqa: BLE001 - diagnostic only
        _out(f"lemonade    not reachable at {c.lemonade_url} ({e.__class__.__name__}); only needed for art")
    return 0 if ok else 1


# ----------------------------------------------------------------- extract

def _select(args: argparse.Namespace, found: dict) -> list[sources.Source]:
    if args.ids:
        bad = [i for i in args.ids if i not in sources.BY_ID]
        if bad:
            raise SystemExit(f"unknown source id(s): {', '.join(bad)}. Known: {', '.join(sources.BY_ID)}")
        chosen = [sources.BY_ID[i] for i in args.ids]
    elif args.phase is not None:
        chosen = [s for s in sources.SOURCES if s.phase == args.phase]
    elif args.all:
        chosen = list(sources.SOURCES)
    else:
        raise SystemExit("give source ids, --phase N, or --all")
    return [s for s in chosen if (s.kind != "map" and not s.duplicate_of) or args.ids]


def cmd_extract(args: argparse.Namespace) -> int:
    from .extract.pdftext import extract_pdf, has_text_layer

    c = cfg.load()
    found, _ = sources.scan(c.references)
    rc = 0
    for s in _select(args, found):
        pdf = found.get(s.id)
        if pdf is None:
            _out(f"{s.id:16} SKIP  file not found in {c.references}")
            rc = 1
            continue
        if not has_text_layer(pdf):
            if not args.ocr:
                _out(f"{s.id:16} SKIP  no text layer: add --ocr to read it with local OCR")
                continue
            from .extract.ocr import ocr_pdf
            summary = ocr_pdf(pdf, s.id, s.title, c.build / "raw" / s.id, c.build / "ocr" / s.id, log=_out)
            _out(f"{s.id:16} {summary['pages']:4d} pages -> {len(summary['sections']):3d} sections (OCR)")
            continue
        summary = extract_pdf(pdf, s.id, s.title, c.build / "raw" / s.id, max_pages=args.max_pages)
        icons = ", ".join(f"{k} {v}" for k, v in sorted(summary["icons"].items())) or "none"
        _out(f"{s.id:16} {summary['pages']:4d} pages -> {len(summary['sections']):3d} sections; icons: {icons}")
    return rc


def cmd_render(args: argparse.Namespace) -> int:
    from .extract.pdftext import parse_pages, render_pages

    c = cfg.load()
    found, _ = sources.scan(c.references)
    pdf = found.get(args.id)
    if pdf is None:
        raise SystemExit(f"source {args.id!r} not found")
    paths = render_pages(pdf, parse_pages(args.pages), c.build / "pages" / args.id, dpi=args.dpi)
    for p in paths:
        _out(str(p))
    return 0


def cmd_guard(args: argparse.Namespace) -> int:
    return guard.run(args.paths or None)


# ------------------------------------------------------------------- dice

def _settings_or_none():
    from . import campaign as cp
    try:
        return cp.load_settings()
    except cp.CampaignError:
        return None


def _log_roll(kind: str, label: str | None, text: str) -> None:
    from . import ops
    ops.log_roll(kind, label, text)


def cmd_roll(args: argparse.Namespace) -> int:
    from . import dice

    s = _settings_or_none()
    if (s and s["dice"]["mode"] == "manual" and not args.adversary and not args.auto
            and args.feat is None):
        need = 1 if args.favoured == args.ill else 2
        n = max(0, args.rating + args.bonus - args.penalty + ((2 if args.inspired else 1) if args.hope else 0))
        _out(f"MANUAL DICE: ask the player to roll {need} Feat di{'e' if need == 1 else 'ce'}"
             f"{' (' + ('favoured' if args.favoured else 'ill-favoured') + ')' if need == 2 else ''}"
             f" and {n} Success dice, then re-run with --feat ... --success ...")
        return 3
    r = dice.test(
        args.rating, args.tn,
        favoured=args.favoured, ill=args.ill, bonus=args.bonus, penalty=args.penalty,
        hope=args.hope, inspired=args.inspired, weary=args.weary, miserable=args.miserable, adversary=args.adversary,
        feat=args.feat, success=args.success,
    )
    text = dice.describe(r)
    _log_roll("adversary" if args.adversary else "test", args.label, text)
    _out(json.dumps(r.as_dict()) if args.json else text)
    return 0


def cmd_odds(args: argparse.Namespace) -> int:
    from . import dice

    _out(dice.describe_odds(args.rating, args.tn, favoured=args.favoured, ill=args.ill,
                            bonus=args.bonus, penalty=args.penalty, inspired=args.inspired,
                            weary=args.weary, miserable=args.miserable))
    return 0


def _tables():
    from . import ops
    from . import tables as tb

    tdir = ops.tables_dir()
    if not tdir.is_dir():
        raise SystemExit(f"no tables yet in {tdir}")
    return tb, ops.all_tables()


def cmd_table(args: argparse.Namespace) -> int:
    tb, tables = _tables()
    if args.id is None:
        for tid, t in sorted(tables.items()):
            _out(f"{tid:32} {t.get('kind', 'roll'):9} {t.get('title', '')}")
        return 0
    if tables.get(args.id, {}).get("kind") == "reference":
        _out(json.dumps(tables[args.id]["rows"], indent=2, ensure_ascii=False))
        return 0
    from . import ops
    for _ in range(args.times):
        _out(ops.roll_table(args.id, favoured=args.favoured, ill=args.ill, column=args.column, given=args.given,
                            label=args.label)[1])
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    from . import ops
    _out(ops.ask(args.chance, args.question, favoured=args.favoured, ill=args.ill, given=args.feat)[3])
    return 0


def _onoff(value: str | None) -> bool | None:
    if value is None:
        return None
    v = value.lower()
    if v not in ("on", "off", "true", "false", "yes", "no"):
        raise SystemExit("use on or off")
    return v in ("on", "true", "yes")


def cmd_easy(args: argparse.Namespace) -> int:
    from . import campaign as cp

    want = _onoff(args.state)
    s = cp.set_value("difficulty.easy", want) if want is not None else cp.load_settings()
    easy = s["difficulty"]["easy"]
    if (s.get("campaign") or {}).get("mode") == "strider":
        _out(f"easy mode: {'ON' if easy else 'off'} -> a lone hero has TN 18 - Attribute and the Strider feature "
             f"anyway; {'fights are kept gentler' if easy else 'fights are as the encounters setting says'}")
        return 0
    _out(f"easy mode: {'ON' if easy else 'off'} -> hero TN = {cp.tn_base(s)} - Attribute, "
         f"Band TN = {cp.tn_base(s)} - Readiness; "
         f"Strider Distinctive Feature {'granted' if cp.has_strider_feature(s) else 'not granted'}")
    return 0


def cmd_dice_mode(args: argparse.Namespace) -> int:
    from . import campaign as cp

    if args.mode:
        if args.mode not in ("auto", "manual"):
            raise SystemExit("mode is auto or manual")
        s = cp.set_value("dice.mode", args.mode)
    else:
        s = cp.load_settings()
    _out(f"dice mode: {s['dice']['mode']}")
    return 0


def cmd_time(args: argparse.Namespace) -> int:
    from . import clock

    if args.advance:
        day, warnings = clock.advance(args.advance, args.at)
        _out(f"day {day}")
        for w in warnings:
            _out(w)
    elif args.at:
        clock.set_time(args.at)
    fm = clock.state()[1]
    _out(f"day {clock.today(fm)}" + (f", {fm['time']}" if fm.get("time") else "") + f" ({fm.get('date', '')})")
    for line in clock.describe(fm):
        _out("  " + line)
    return 0


def cmd_deadline(args: argparse.Namespace) -> int:
    from . import clock

    if args.action == "add":
        e = clock.add_deadline(args.name, in_days=args.in_days, due=args.due, note=args.note or "")
        _out(f"deadline: {e['name']} on day {e['due']}")
    elif args.action == "done":
        gone = clock.remove("deadlines", args.name)
        _out(f"removed {gone['name']}" if gone else f"no deadline {args.name!r}")
    return 0


def cmd_counter(args: argparse.Namespace) -> int:
    from . import clock

    if args.action == "add":
        e = clock.add_counter(args.name, since=args.since)
        _out(f"counter: {e['name']} since day {e['since']}")
    elif args.action == "done":
        gone = clock.remove("counters", args.name)
        _out(f"removed {gone['name']}" if gone else f"no counter {args.name!r}")
    return 0


def cmd_obsidian(args: argparse.Namespace) -> int:
    from . import campaign as cp
    from . import obsidian as ob

    try:
        if args.action == "setup":
            for line in ob.setup():
                _out(line)
            _out("Reload Obsidian (or the two plugins) to pick it up. Then run `ringwraith obsidian sync`.")
        elif args.action == "sync":
            changed = ob.sync()
            _out(chr(10).join(changed) if changed else "calendar events already up to date")
        elif args.action == "home":
            _out(f"wrote {ob.home().name}")
        elif args.action == "calendar":
            if args.day1:
                ob.parse_date(args.day1)          # validate before saving
                cp.set_value("calendar.day1", args.day1)
            st = ob._state()
            day = int(st.get("day") or 1)
            _out(f"day 1 = {ob.show(ob.day1())}; today (day {day}) = {ob.show(ob.tale_date(day))}")
            for d in sorted(st.get("deadlines") or [], key=lambda d: d.get("due", 0)):
                _out(f"  {d.get('name')}: day {d.get('due')} = {ob.show(ob.tale_date(int(d['due'])))}")
        elif args.action == "statblock":
            if not args.note or not args.atom:
                raise SystemExit('usage: ringwraith obsidian statblock --note "<Adversary>" --atom <lore slug>')
            _out(f"stat block from {args.atom} written into {ob.statblock(args.note, args.atom).name}")
    except ob.ObsidianError as e:
        raise SystemExit(str(e)) from e
    return 0


def cmd_chronicle(args: argparse.Namespace) -> int:
    from . import chronicle, clock
    from . import campaign as cp

    events = chronicle.load_events()
    plays = chronicle.sessions(events)
    if not events:
        raise SystemExit("no table log yet (the chronicle is written from web-table play)")
    start, end = plays[args.play]
    text = chronicle.render(events, start, end)
    if args.print:
        _out(text)
        return 0
    number = args.session or int(clock.state()[1].get("session") or 1)
    from . import vault
    note = vault.session_note(number)
    if not note.exists():
        raise SystemExit(f"{note.name} doesn't exist; create it first (ringwraith note new session ...)")
    chronicle.write(note, text)
    _out(f"wrote the chronicle of play session {args.play if args.play >= 0 else len(plays) + args.play} "
         f"({end - start} events, {text.count('![[')} images) into {note.name}")
    _draw_road(number)        # the session's road map goes with its chronicle
    return 0


def _draw_road(n: int) -> None:
    """Draw session n's road map(s), refresh the map notes, and write The road into the session note."""
    from . import geo
    from . import chronicle
    from . import campaign as cp

    files = geo.session_maps(n)
    for f in files:
        _out(f"session map: {f}")
    for f in geo.write_notes():
        _out(f"note: {f.name}")
    from . import vault
    note = vault.session_note(n)
    if note.exists() and files:
        chronicle.write(note, geo.session_note_section(n, files), heading="## The road", before="## People met")
        _out(f"added the road to {note.name}")
    elif not files:
        _out("no road this session (no journeys between places)")


def cmd_map(args: argparse.Namespace) -> int:
    from . import geo

    if args.map_cmd == "build":
        made = geo.build_images(force=args.force, log=_out)
        _out(f"{len(made)} map image(s) written" if made else "map images already in the vault (use --force)")
    elif args.map_cmd == "place":
        e = geo.add_place(args.name, map_id=args.map, at=args.at, near=args.near, bearing=args.bearing,
                          miles=args.miles, state=args.state, note=args.note or "")
        _out(f"{e['name']}: {e['map']} {e['at']} ({e.get('state') or 'no state'})")
    elif args.map_cmd == "move":
        from . import vault
        leg = geo.move([w.strip() for w in args.who.split(",")], args.to, frm=args.frm,
                       via=[v.strip() for v in (args.via or "").split(",") if v.strip()], mode=args.mode,
                       note=args.note or "", hero=vault.hero_name())
        _out(f"day {leg['day']}: {', '.join(leg['who'])} {leg['from']} -> {leg['to']} ({leg['mode']}, on {leg['map']})")
    elif args.map_cmd == "where":
        data = geo.load()
        for who, w in data["whereabouts"].items():
            _out(f"{who}: {w.get('place')}")
        for name, st in data["states"].items():
            _out(f"  [{st}] {name}")
    elif args.map_cmd == "session":
        from . import clock
        _draw_road(args.session or int(clock.state()[1].get("session") or 1))
    elif args.map_cmd == "journey":
        plan = geo.journey_plan(args.frm, args.to, via=[v.strip() for v in (args.via or "").split(",") if v.strip()])
        _out(f"{plan['from']} -> {plan['to']}: {plan['hexes']} hexes, {plan['miles']} miles")
        _out("lands entered (Loremaster only): " + ", ".join(f"{n} {t}" for t, n in plan["lands"].items()))
        _out("in order: " + geo.route_in_order(plan))
        if plan["road_hexes"]:
            _out(f"road: {plan['road_hexes']} of {plan['hexes']} hexes (a journey event on a road hex gains (1d))")
        if args.show:
            geo.set_plan(plan)
            _out("plan shown on the map")
    elif args.map_cmd == "region":
        from . import regions
        g = regions.load(args.id)
        spec = {k: g.get(k) for k in regions.LIST_KEYS}
        anchor = g["anchor"]["place"] if isinstance(g.get("anchor"), dict) else g.get("anchor")
        spec.update(title=g["title"], anchor=anchor, id=g.get("id") or regions.slug_of(g["title"]),
                    parent=g.get("parent", "eriador"), scale=g.get("scale"), land=g.get("land"),
                    bounds=g.get("bounds") if isinstance(g.get("anchor"), dict) else None)
        g = regions.create(spec)
        _out(f"drew {g['title']} ({g['id']}): bounds {g['bounds']} miles")
    elif args.map_cmd == "notes":
        for f in geo.write_notes():
            _out(f"note: {f.name}")
    elif args.map_cmd == "log":
        for leg in geo.legs():
            _out(f"day {leg['day']} {leg.get('time', '')}: {', '.join(leg['who'])} {leg['from']} -> {leg['to']} ({leg['mode']})")
    return 0


def cmd_site(args: argparse.Namespace) -> int:
    from . import sites

    if args.site_cmd == "list":
        for st in sites.all_sites():
            seen = sum(1 for r in st["rooms"] if r.get("explored"))
            _out(f"{st['id']:24} {st['title']} (at {st['place']}): {seen}/{len(st['rooms'])} rooms explored")
    elif args.site_cmd == "render":
        _out(str(sites.render_to_vault(sites.load(args.id))))
    elif args.site_cmd == "explore":
        st = sites.explore(args.id, args.rooms)
        _out(str(sites.render_to_vault(st)))
    return 0


def cmd_tn(args: argparse.Namespace) -> int:
    from . import campaign as cp

    s = cp.load_settings()
    _out(str(cp.hero_tn(args.attribute, s)))
    return 0


def cmd_art(args: argparse.Namespace) -> int:
    from . import art

    c = cfg.load()
    if args.art_cmd == "models":
        for m in art.image_models(c.lemonade_url):
            d = m.get("image_defaults", {})
            _out(f"{m['id']:28} downloaded={m.get('downloaded')}  defaults={d}")
        return 0
    if args.art_cmd == "test":
        models = args.models or [m["id"] for m in art.image_models(c.lemonade_url)
                                 if m.get("downloaded") and "esrgan" not in m["id"].lower()]
        if not models:
            raise SystemExit("no downloaded image models")
        art.shootout(c.lemonade_url, models, c.build / "art-test", log=_out)
        return 0
    if args.art_cmd == "queue":
        from . import artqueue
        job = artqueue.enqueue(args.preset, args.subject, note=args.note, name=args.name,
                               priority=args.priority, seed=args.seed, mood=args.mood, time=args.time,
                               characters=[w.strip() for w in (args.with_ or "").split(",") if w.strip()])
        target = f" -> {job['note']}" if job["note"] else ""
        _out(f"queued {job['id']}: {job['file']}{target}")
        return 0
    if args.art_cmd == "worker":
        from . import artqueue
        n = artqueue.run_worker(once=args.once, idle_exit_minutes=args.idle_exit, log=_out)
        _out(f"art worker finished ({n} image(s))")
        return 0
    if args.art_cmd == "pending":
        from . import artqueue
        for j in artqueue.pending():
            _out(f"{j['id']} p{j['priority']} {j['preset']:9} {j['file']}  <- {j['subject'][:60]}")
        return 0
    if args.art_cmd == "gen":
        model = args.model
        if not model:
            from . import campaign as cp
            try:
                model = cp.load_settings()["art"]["model"]
            except cp.CampaignError:
                model = None
        if not model:
            raise SystemExit("give --model (or set art.model in the campaign settings)")
        out = Path(args.out) if args.out else c.build / "art" / f"{args.preset}-{int(time.time())}.png"
        r = art.render(c.lemonade_url, model, args.preset, args.subject, out, seed=args.seed, steps=args.steps)
        _out(f"{r.path}  ({r.seconds}s, seed {r.seed})")
        return 0
    return 1


# --------------------------------------------------------------- campaigns

def cmd_new(args: argparse.Namespace) -> int:
    from . import vault

    dest = vault.create(args.slug, name=args.name, mode=args.mode, region=args.region,
                        start=args.start, year=args.year, easy=args.easy)
    _out(f"created {dest} (active). Open this folder as a vault in Obsidian.")
    return 0


def cmd_campaigns(args: argparse.Namespace) -> int:
    from . import vault

    rows = vault.list_campaigns()
    if not rows:
        _out("no campaigns yet: `ringwraith new <slug>`")
    for r in rows:
        mark = "*" if r["active"] else " "
        _out(f"{mark} {r['slug']:24} {r.get('name', '')} "
             f"({r.get('mode', '?')}, {r.get('start', '?')} {r.get('year', '')})")
    return 0


def cmd_switch(args: argparse.Namespace) -> int:
    from . import campaign as cp

    cp.set_active(args.slug)
    _out(f"active campaign: {args.slug}")
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    from . import vault

    _out(f"archived to {vault.archive(args.slug, delete=not args.keep)}")
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    from . import vault

    if not args.yes:
        raise SystemExit(f"this archives '{args.slug}' to a zip and recreates it empty; add --yes to confirm")
    z, dest = vault.reset(args.slug)
    _out(f"archived old vault to {z}")
    _out(f"fresh vault at {dest} (active)")
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    from . import vault

    if args.note_cmd == "new":
        extra = {k: vault.parse_value(v) for k, v in (kv.split("=", 1) for kv in args.set or [])}
        _out(str(vault.new_note(args.kind, args.name, extra=extra)))
        return 0
    path = vault.resolve_note(args.ref)
    fm, body = vault.read_note(path)
    if args.note_cmd == "get":
        value = vault.get_path(fm, args.key) if args.key else fm
        _out(json.dumps(value, ensure_ascii=False, indent=2, default=str))
        return 0
    if args.note_cmd == "encounter":
        from . import clock
        st = clock.state()[1]
        session = args.session or int(st.get("session") or 1)
        day = args.day if args.day is not None else clock.today(st)
        section = "## Deeds" if fm.get("type") in ("ally", "hero") else (
            "## What the hero has seen of it" if fm.get("type") == "adversary" else vault.ENCOUNTERS)
        _out(f"{path.name}: {vault.add_encounter(path, args.text, session, day, section)}")
        return 0
    if args.note_cmd == "sort-encounters":
        new = vault.sort_encounters(body)
        if new != body:
            vault.write_note(path, fm, new)
        _out(f"{path.name}: encounters in story order")
        return 0
    if args.note_cmd == "set":
        from . import fileio
        bad = [kv for kv in args.pairs if "=" not in kv]
        if bad:
            raise SystemExit(f"expected key=value, got: {' '.join(bad)}")
        with fileio.locked():
            fm, body = vault.read_note(path)          # re-read under the lock: another writer may have saved it
            for kv in args.pairs:
                key, raw = kv.split("=", 1)
                vault.set_path(fm, key, vault.parse_value(raw))
            vault.write_note(path, fm, body)
        _out(f"updated {path.name}: " + ", ".join(args.pairs))
        return 0
    return 1


def cmd_status(args: argparse.Namespace) -> int:
    from . import artqueue
    from . import campaign as cp
    from . import vault

    try:
        d = cp.campaign_dir()
    except cp.CampaignError:
        _out("Ringwraith: no active campaign. Start one with /session-zero." if args.hook
             else "no active campaign")
        return 0
    s = cp.load_settings()
    meta = s.get("campaign", {})
    state_path = d / ".ringwraith" / "state.md"
    state, _ = vault.read_note(state_path) if state_path.exists() else ({}, "")
    sessions = sorted((d / "10 Campaign" / "Sessions").glob("Session *.md"))
    easy = "on" if s["difficulty"]["easy"] else "off"
    art_on = "on" if s["art"]["enabled"] else "off"
    _out(f"Ringwraith campaign: {meta.get('name', d.name)} [{d.name}] at {d}")
    _out(f"mode={meta.get('mode')} easy={easy} encounters={s['difficulty'].get('encounters', 'story')} "
         f"dice={s['dice']['mode']} art={art_on} "
         f"(model {s['art'].get('model') or 'Z-Image-Turbo-Q8B'})")
    _out("state: " + ", ".join(f"{k}={v}" for k, v in state.items()))
    _out(f"last session note: {sessions[-1].relative_to(d) if sessions else 'none'}")
    jobs = artqueue.pending()
    worker = "running" if artqueue.worker_alive() else "stopped"
    _out(f"art queue: {len(jobs)} pending; worker {worker}")
    if args.hook:
        _out("Playing? Use /session-start (or /session-zero for a new campaign).")
    return 0


def cmd_settings(args: argparse.Namespace) -> int:
    from . import campaign as cp
    from . import vault

    if args.key and args.value is not None:
        s = cp.set_value(args.key, vault.parse_value(args.value))
    else:
        s = cp.load_settings()
    value = vault.get_path(s, args.key) if args.key else s
    _out(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from . import campaign as cp
    from .web.server import serve

    # The table stays on one campaign for its whole run: its log, images, tools and the CLI commands the model
    # runs (they inherit this environment) all use it, even if another campaign is made active meanwhile.
    slug = args.campaign or cp.active_slug()
    if not slug:
        raise SystemExit("no active campaign: create one with `ringwraith new <slug>` first")
    os.environ["RINGWRAITH_CAMPAIGN"] = slug
    cp.campaign_dir()   # fail early if it doesn't exist
    serve(host=args.host, port=args.port, open_browser=not args.no_browser)
    return 0


def cmd_lore_index(args: argparse.Namespace) -> int:
    """Regenerate lore/INDEX.md's lists (everything from '## Procedures' on); the guide above stays."""
    import re as _re
    import yaml as _yaml
    c = cfg.load()
    idx = c.lore / "INDEX.md"
    head = idx.read_text(encoding="utf-8").split("\n## Procedures", 1)[0].rstrip() + "\n"
    out = [head, "## Procedures", "Rules, one file per procedure: Steps first, then the solo (Strider Mode) rules.", ""]
    for f in sorted((c.lore / "procedures").rglob("*.md")):
        out.append(f"- `{f.relative_to(c.lore).as_posix()}`")
    out += ["", "## Campaigns", "Each book's campaign, setting and subsystem material, by book.", ""]
    for d in sorted(p for p in (c.lore / "campaigns").iterdir() if p.is_dir()) if (c.lore / "campaigns").is_dir() else []:
        out.append(f"- **{d.name}**: " + ", ".join(f"`{f.relative_to(c.lore).as_posix()}`" for f in sorted(d.glob("*.md"))))
    out += ["", "## Adventures (Loremaster-only; run only if the story leads there)"]
    for f in sorted((c.lore / "adventures").rglob("*.md")) if (c.lore / "adventures").is_dir() else []:
        text = f.read_text(encoding="utf-8")
        m = _re.search(r"^name:\s*(.+)$", text, _re.M)
        w = _re.search(r"^when:\s*(.+)$", text, _re.M)
        out.append(f"- `{f.relative_to(c.lore).as_posix()}`: {m.group(1).strip() if m else f.stem}"
                   + (f" ({w.group(1).strip().strip(chr(34))})" if w else ""))
    out += ["", "## Atoms"]
    for d in sorted(p for p in (c.lore / "atoms").iterdir() if p.is_dir()):
        out.append(f"- `atoms/{d.name}/` ({len(list(d.glob('*.md')))})")
    for f in sorted((c.lore / "atoms").glob("*.md")):
        out.append(f"- `atoms/{f.name}`")
    # Table ids only, grouped by family: the ids name their tables well, and a title per row tripled the
    # index's size. (At the table the model rolls with `roll_table`; a table's own title shows when rolled.)
    out += ["", "## Tables",
            "Roll with `roll_table` (id). `*` = homebrew (user-approved), `(ref)` = reference data printed whole.", ""]
    families: dict[str, list[str]] = {}
    for f in sorted((c.lore / "tables").glob("*.yaml")):
        t = _yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        tid = str(t.get("id", f.stem))
        mark = ("*" if t.get("homebrew") else "") + (" (ref)" if t.get("kind", "roll") != "roll" else "")
        families.setdefault(tid.split("-")[0], []).append(tid + mark)
    for fam, ids in families.items():
        out.append(f"- **{fam}**: " + ", ".join(ids))
    from . import fileio
    fileio.atomic_write(idx, "\n".join(out) + "\n")
    _out(f"rewrote {idx} lists")
    return 0


def cmd_lore_check(args: argparse.Namespace) -> int:
    from . import ops
    from . import tables as tb
    tables = ops.all_tables() if ops.tables_dir().is_dir() else {}     # a new library has none yet
    errors = []
    for t in tables.values():
        errors += tb.validate(t)
    unverified = [tid for tid, t in tables.items() if not t.get("verified")]
    for e in errors:
        _out(f"ERROR {e}")
    _out(f"{len(tables)} tables, {len(errors)} error(s), {len(unverified)} unverified"
         + (f": {', '.join(sorted(unverified))}" if unverified and args.verbose else ""))

    # How the library is organised: paths that point nowhere, rulings to review, tables nothing names,
    # and secrets that could leak into player-facing text.
    from . import lorecheck
    repo = cfg.REPO_ROOT
    rel = lambda p: p.relative_to(repo).as_posix()  # noqa: E731
    broken = lorecheck.broken_paths(repo)
    for f, n, ref in broken:
        _out(f"ERROR {rel(f)}:{n}: points to {ref}, which doesn't exist")
    reads = lorecheck.readings(repo)
    if args.readings:
        for f, n, line in reads:
            _out(f"reading {rel(f)}:{n}: {line[:160]}")
    orphans = lorecheck.orphan_tables(repo, sorted(tables))
    no_lm, mixed = lorecheck.secret_split(repo)
    if args.verbose:
        for tid in orphans:
            _out(f"note: table {tid} is not named anywhere (nothing says when to roll it)")
        for f in no_lm:
            _out(f"warning: {rel(f)} is marked secrets: true but has no Loremaster-only section")
        for f in mixed:
            _out(f"warning: {rel(f)} has a '## From …' block with no Loremaster-only part")
    _out(f"{len(broken)} broken path(s), {len(reads)} reading(s) to review"
         f"{' (list them with --readings)' if not args.readings else ''}, {len(orphans)} unnamed table(s), "
         f"{len(no_lm) + len(mixed)} atom(s) with a weak secret split" + ("" if args.verbose else " (details with -v)"))
    return 1 if errors or broken else 0


# -------------------------------------------------------------------- main

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ringwraith", description="Solo Loremaster toolkit for The One Ring")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("doctor", help="check configuration, sources and services")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("extract", help="extract reference PDFs into raw Markdown sections (build/raw)")
    p.add_argument("ids", nargs="*", help="source ids (see `doctor`)")
    p.add_argument("--phase", type=int, help="extract a group of books: 1 = the ones needed to play, 7 = the others")
    p.add_argument("--all", action="store_true", help="extract every text source")
    p.add_argument("--max-pages", type=int, default=30, help="split chapters longer than this")
    p.add_argument("--ocr", action="store_true", help="read a PDF that has no text layer with local OCR (slow: ~6 s a page)")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("render", help="render pages to PNG for vision reading")
    p.add_argument("id")
    p.add_argument("pages", help="e.g. 12 or 10-14,20")
    p.add_argument("--dpi", type=int, default=110)
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("guard", help="run the commit guard (staged files, or the given paths)")
    p.add_argument("paths", nargs="*")
    p.set_defaults(func=cmd_guard)

    p = sub.add_parser("roll", help="roll a TOR test: Feat die + N Success dice")
    p.add_argument("rating", type=int, help="Success dice (skill/proficiency/disposition rating)")
    p.add_argument("--tn", type=int)
    p.add_argument("--favoured", action="store_true")
    p.add_argument("--ill", action="store_true", help="ill-favoured")
    p.add_argument("--bonus", type=int, default=0, help="gain (Nd)")
    p.add_argument("--penalty", type=int, default=0, help="lose (Nd)")
    p.add_argument("--hope", action="store_true", help="spend 1 Hope: gain (1d), (2d) if --inspired")
    p.add_argument("--inspired", action="store_true")
    p.add_argument("--weary", action="store_true")
    p.add_argument("--miserable", action="store_true")
    p.add_argument("--adversary", action="store_true", help="read the Feat die the Shadow's way")
    p.add_argument("--feat", nargs="+", help="physical result(s): 1-10, eye, gandalf")
    p.add_argument("--success", nargs="*", type=int, help="physical Success dice results")
    p.add_argument("--json", action="store_true")
    p.add_argument("--auto", action="store_true", help="roll by script even in manual dice mode")
    p.add_argument("--label", help="what the roll is for (logged)")
    p.set_defaults(func=cmd_roll)

    p = sub.add_parser("odds", help="chance of success for a hero test, with and without Hope")
    p.add_argument("rating", type=int, help="Success dice before Hope")
    p.add_argument("--tn", type=int, required=True)
    p.add_argument("--favoured", action="store_true")
    p.add_argument("--ill", action="store_true", help="ill-favoured")
    p.add_argument("--bonus", type=int, default=0, help="gain (Nd)")
    p.add_argument("--penalty", type=int, default=0, help="lose (Nd)")
    p.add_argument("--inspired", action="store_true")
    p.add_argument("--weary", action="store_true")
    p.add_argument("--miserable", action="store_true")
    p.set_defaults(func=cmd_odds)

    p = sub.add_parser("table", help="roll on a lore table (no id: list tables)")
    p.add_argument("id", nargs="?")
    p.add_argument("--column")
    p.add_argument("--favoured", action="store_true")
    p.add_argument("--ill", action="store_true")
    p.add_argument("--given", nargs="+", help="physical results, one per die in table order")
    p.add_argument("--times", type=int, default=1)
    p.add_argument("--label", help="what the roll is for (logged)")
    p.set_defaults(func=cmd_table)

    p = sub.add_parser("ask", help="Telling table yes/no question")
    p.add_argument("chance", nargs="?", help="certain | likely | middling | doubtful | unthinkable")
    p.add_argument("--favoured", action="store_true")
    p.add_argument("--ill", action="store_true")
    p.add_argument("--feat", help="physical Feat die result")
    p.add_argument("--question", "-q", help="the question asked (logged)")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("new", help="create a campaign vault and make it active")
    p.add_argument("slug")
    p.add_argument("--name")
    p.add_argument("--mode", default="band", choices=["band", "strider"])
    p.add_argument("--region", default="eriador")
    p.add_argument("--start", default="bree")
    p.add_argument("--year", type=int, default=2965)
    p.add_argument("--easy", action="store_true")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("campaigns", help="list campaigns (* = active)")
    p.set_defaults(func=cmd_campaigns)

    p = sub.add_parser("switch", help="make another campaign active")
    p.add_argument("slug")
    p.set_defaults(func=cmd_switch)

    p = sub.add_parser("archive", help="zip a campaign into <vaults>/_archive and remove it")
    p.add_argument("slug")
    p.add_argument("--keep", action="store_true", help="zip only, keep the vault")
    p.set_defaults(func=cmd_archive)

    p = sub.add_parser("reset", help="archive a campaign and recreate it empty (same settings)")
    p.add_argument("slug")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_reset)

    p = sub.add_parser("note", help="create notes and read/write their frontmatter")
    nsub = p.add_subparsers(dest="note_cmd", required=True)
    n = nsub.add_parser("new", help="new note from a template")
    n.add_argument("kind", choices=["hero", "ally", "mission", "journey", "session", "npc", "place", "adversary", "item"])
    n.add_argument("name")
    n.add_argument("--set", nargs="*", help="key=value frontmatter (dotted keys, YAML values)")
    n = nsub.add_parser("get", help="print frontmatter (or one dotted key)")
    n.add_argument("ref")
    n.add_argument("key", nargs="?")
    n = nsub.add_parser("set", help="set frontmatter values: key=value ...")
    n.add_argument("ref")
    n.add_argument("pairs", nargs="+")
    n = nsub.add_parser("encounter", help="add a dated line to a person's Encounters (an Ally's Deeds, a foe's "
                                          "'What the hero has seen'), kept in story order, oldest first")
    n.add_argument("ref")
    n.add_argument("text", help="what happened, in a sentence or two (wiki-link people and places)")
    n.add_argument("--session", type=int, help="default: the current session")
    n.add_argument("--day", type=int, help="the tale day (default: today in the tale)")
    n = nsub.add_parser("sort-encounters", help="put a note's Encounters in story order")
    n.add_argument("ref")
    p.set_defaults(func=cmd_note)

    p = sub.add_parser("status", help="active campaign summary")
    p.add_argument("--hook", action="store_true", help="SessionStart hook output")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("settings", help="show or change campaign settings (dotted key, YAML value)")
    p.add_argument("key", nargs="?")
    p.add_argument("value", nargs="?")
    p.set_defaults(func=cmd_settings)

    p = sub.add_parser("easy", help="show or switch easy mode (TN 18 - Attribute + Strider feature)")
    p.add_argument("state", nargs="?", help="on | off")
    p.set_defaults(func=cmd_easy)

    p = sub.add_parser("dice-mode", help="show or set dice mode: auto (scripted) or manual (physical dice)")
    p.add_argument("mode", nargs="?")
    p.set_defaults(func=cmd_dice_mode)

    p = sub.add_parser("tn", help="Target Number for an Attribute (hero) or Readiness (Band); respects easy mode")
    p.add_argument("attribute", type=int)
    p.set_defaults(func=cmd_tn)

    p = sub.add_parser("time", help="day of the tale, deadlines and counters (shown in the web table)")
    p.add_argument("--advance", type=int, metavar="DAYS", help="move the tale on by DAYS")
    p.add_argument("--at", metavar="TIME", help="time of day, e.g. dawn, midday, nightfall")
    p.set_defaults(func=cmd_time)

    p = sub.add_parser("deadline", help="add or finish a deadline the hero knows about")
    p.add_argument("action", choices=["add", "done"])
    p.add_argument("name")
    p.add_argument("--in", dest="in_days", type=int, metavar="DAYS")
    p.add_argument("--due", type=int, metavar="DAY", help="the day it falls on (instead of --in)")
    p.add_argument("--note")
    p.set_defaults(func=cmd_deadline)

    p = sub.add_parser("counter", help="add or finish a count-up (e.g. days someone has been missing)")
    p.add_argument("action", choices=["add", "done"])
    p.add_argument("name")
    p.add_argument("--since", type=int, metavar="DAY", help="the day it started (default today)")
    p.set_defaults(func=cmd_counter)

    p = sub.add_parser("chronicle", help="write a session as played at the web table (story, images, rolls) "
                                         "into its session note")
    p.add_argument("--session", type=int, help="session note number (default: the current session in state)")
    p.add_argument("--play", type=int, default=-1,
                   help="which play session in the table log, counted from /session-start (default: the last)")
    p.add_argument("--print", action="store_true", help="print instead of writing the note")
    p.set_defaults(func=cmd_chronicle)

    p = sub.add_parser("obsidian", help="Obsidian extras: Shire Reckoning calendar (Calendarium), stat blocks "
                                        "(Fantasy Statblocks), the Home dashboard")
    p.add_argument("action", choices=["setup", "sync", "home", "calendar", "statblock"],
                   help="setup: write the plugins' settings; sync: calendar events from session/journey/mission "
                        "notes; home: rewrite the dashboard; calendar: show or set day 1; statblock: copy a "
                        "lore stat block into an adversary note")
    p.add_argument("--day1", help="with calendar: the Shire date of tale day 1, e.g. '1 Astron 2965'")
    p.add_argument("--note", help="with statblock: the adversary note")
    p.add_argument("--atom", help="with statblock: the lore adversary slug (lore/atoms/adversaries/<slug>.md)")
    p.set_defaults(func=cmd_obsidian)

    p = sub.add_parser("map", help="maps, places, whereabouts and the travel log")
    msub = p.add_subparsers(dest="map_cmd", required=True)
    m = msub.add_parser("build", help="put the map images into the campaign vault")
    m.add_argument("--force", action="store_true")
    m = msub.add_parser("place", help="add or move a campaign place")
    m.add_argument("name")
    m.add_argument("--map")
    m.add_argument("--at", type=float, nargs=2, metavar=("X", "Y"), help="pixels on the map")
    m.add_argument("--near", help="a known place to measure from")
    m.add_argument("--bearing", help="N, NE, ESE ... from --near")
    m.add_argument("--miles", type=float)
    m.add_argument("--state", default="heard", choices=["heard", "visited", "current"])
    m.add_argument("--note")
    m = msub.add_parser("move", help="record a move: who (comma-separated) goes to a place")
    m.add_argument("who")
    m.add_argument("to")
    m.add_argument("--from", dest="frm")
    m.add_argument("--via", help="comma-separated places along the way")
    m.add_argument("--mode", default="on foot")
    m.add_argument("--note")
    msub.add_parser("where", help="where everyone is, and known places")
    m = msub.add_parser("session", help="draw this session's map(s) and refresh the map notes in Obsidian")
    m.add_argument("--session", type=int)
    msub.add_parser("notes", help="refresh the map notes and travel log in 60 Maps/")
    m = msub.add_parser("region", help="draw (or redraw) a region map from .ringwraith/regions/<id>.yaml")
    m.add_argument("id")
    m = msub.add_parser("journey", help="count a journey in Eriador hexes, with the land types (Loremaster only)")
    m.add_argument("frm", metavar="from")
    m.add_argument("to")
    m.add_argument("--via")
    m.add_argument("--show", action="store_true", help="draw the planned route on the player's map")
    msub.add_parser("log", help="the travel log")
    p.set_defaults(func=cmd_map)

    p = sub.add_parser("site", help="site plans (buildings, ruins, delves); write the plan file, then render")
    ssub = p.add_subparsers(dest="site_cmd", required=True)
    ssub.add_parser("list")
    sp = ssub.add_parser("render", help="draw a site plan into the vault")
    sp.add_argument("id")
    sp = ssub.add_parser("explore", help="reveal rooms and redraw")
    sp.add_argument("id")
    sp.add_argument("rooms", nargs="+")
    p.set_defaults(func=cmd_site)

    p = sub.add_parser("art", help="image generation via Lemonade")
    asub = p.add_subparsers(dest="art_cmd", required=True)
    a = asub.add_parser("models", help="list Lemonade image models")
    a = asub.add_parser("test", help="model shootout: 6 fixed prompts per model -> build/art-test/")
    a.add_argument("models", nargs="*")
    a = asub.add_parser("queue", help="queue an image for the background worker")
    a.add_argument("preset", choices=["portrait", "scenery", "adversary", "item", "scene"])
    a.add_argument("subject")
    a.add_argument("--note", help="note to attach the image to (name or path)")
    a.add_argument("--name", help="file name stem")
    a.add_argument("--priority", type=int, default=5, help="lower runs first")
    a.add_argument("--seed", type=int)
    a.add_argument("--mood", choices=["calm", "wonder", "tense", "danger", "battle", "dread", "sorrow"],
                   help="light and atmosphere (default calm; adversary: danger)")
    a.add_argument("--time", choices=["dawn", "day", "dusk", "night"], help="time of day (night: candlelit darkness)")
    a.add_argument("--with", dest="with_", metavar="NAMES",
                   help="named characters in the picture (comma-separated); their portraits are used as references")
    a = asub.add_parser("worker", help="render queued images (run in the background)")
    a.add_argument("--once", action="store_true", help="drain the queue and exit")
    a.add_argument("--idle-exit", type=float, default=240, help="exit after this many idle minutes")
    a = asub.add_parser("pending", help="list queued images")
    a = asub.add_parser("gen", help="generate one image")
    a.add_argument("preset", choices=["portrait", "scenery", "adversary", "item", "scene"])
    a.add_argument("subject")
    a.add_argument("--model")
    a.add_argument("--seed", type=int)
    a.add_argument("--steps", type=int)
    a.add_argument("--out")
    p.set_defaults(func=cmd_art)

    p = sub.add_parser("serve", help="open the Ringwraith Table web app for the active campaign")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=2965)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--campaign", help="serve this campaign instead of the active one (doesn't change .active)")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("lore-index", help="regenerate the file lists in lore/INDEX.md")
    p.set_defaults(func=cmd_lore_index)

    p = sub.add_parser("lore-check", help="validate lore/tables/*.yaml and the lore's paths, readings and secret split")
    p.add_argument("-v", "--verbose", action="store_true", help="also list unnamed tables and weak secret splits")
    p.add_argument("--readings", action="store_true", help="list every distiller's reading, for review")
    p.set_defaults(func=cmd_lore_check)
    return ap


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    from .art import ArtError
    from .campaign import CampaignError
    from .config import ConfigError
    from .tables import TableError
    try:
        return args.func(args)
    except (ConfigError, CampaignError, ArtError, TableError, KeyError, ValueError) as e:
        sys.stderr.write(f"ringwraith: {e}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
