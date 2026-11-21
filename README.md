<div align="center">

<img src="docs/images/logo.svg" alt="Ringwraith" width="400">

**A solo Loremaster for The One Ring, 2nd edition.**
Claude runs the world, the oracles and the bookkeeping while you play your hero, at a table in
your browser with painted scenes, a dice tray, maps and a campaign vault in Obsidian.

[![License: MIT](https://img.shields.io/badge/license-MIT-9b7ac6)](LICENSE)
![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-5c5c8a)
![Claude Code](https://img.shields.io/badge/Claude-Code-b8913a)
![Obsidian](https://img.shields.io/badge/vault-Obsidian-7a5cc6)
![Platform](https://img.shields.io/badge/runs%20on-Windows%20desktop%20with%20a%20GPU-5a9e5a)

<img src="docs/images/inn.jpg" alt="The table at the Prancing Pony: a painted scene, a sketch in the tale of the hall a Dwarf tells of, and the hero and Band panels" width="820">

</div>

> This repository contains **only code and prompts**. You need your own copies of the books: Ringwraith
> builds its library from your PDFs, and everything made from them stays on your machine.

## Screenshots

| | |
|---|---|
| ![The whole painting of the Twenty-first Hall](docs/images/view.jpg) | ![Paths offered as cards](docs/images/paths.jpg) |
| **Take in the view:** click the painting to see all of it | **Paths:** a few ways forward as cards, or type anything else |
| ![A council at the Prancing Pony](docs/images/council.jpg) | ![The dice tray waiting for a roll](docs/images/roll.jpg) |
| **Councils:** how far they are swayed, and the exchanges left | **The dice tray:** the odds with and without Hope, before you choose |
| ![A Band battle at the Dimrill Gate](docs/images/battle.jpg) | ![The Journey panel on the road to Lórien](docs/images/journey.jpg) |
| **Battles:** the Fight panel shows what the hero can see | **Journeys:** each day, camp and event on the road, and a cutaway |
| ![The map of the tale](docs/images/map.jpg) | ![The Tale drawer](docs/images/tale.jpg) |
| **The map:** the road so far, who is where, the planned route | **The Tale:** the journey under way, open threads and the Compass |

## Features

- **A Loremaster that follows the rules.** Ringwraith runs journeys, councils, combat, Band battles,
  missions and the Fellowship Phase by the Core Rules, Strider Mode and the Moria solo rules.
- **Real dice, or yours.** Every roll comes to a tray that shows the odds and lets you decide on Hope. Roll
  there, or roll physical dice and enter them. Oracles and lore tables are rolled in the open.
- **Panels for what matters now.** Live hero and Band sheets, a Fight panel during combat and battles, a Council
  panel while you argue your case, a Journey panel with every march, event and camp on the road and the fatigue
  it cost, and a Fellowship panel that keeps your place in the Fellowship Phase across sessions.
- **Painted scenes.** Scenes, portraits and adversaries are painted on your own GPU, in the style of the
  modern books, and what's told by the fire gets a pencil sketch in the tale. Bring your own style LoRA for
  extra looks. Nothing leaves your machine.
- **A map of the tale.** Region maps with the places you've seen, everyone's whereabouts, the travel log day
  by day, the hex grid and a fog of unknown lands.
- **Story first.** Ringwraith tells outcomes as story and keeps mechanics in a short Loremaster note. With
  `cutaways: on` in your Compass, it now and then shows a scene the hero can't see, to raise the tension.
- **A campaign you can read.** Each campaign is an Obsidian vault: session chronicles, people, places,
  threads, journeys and maps, with Ringwraith's own secrets kept out of sight.

## What you need

| | |
|---|---|
| [Claude Code](https://claude.com/claude-code) | Installed and logged in on this computer. Ringwraith plays through your Claude login |
| [Python 3.12+](https://www.python.org/downloads/) | |
| The books | Your PDFs of The One Ring 2e. To play: the **Core Rules**, **Strider Mode**, **Moria** and the **Loremaster's Screen**. Other books add places, adventures and tables |
| [Lemonade](https://lemonade-server.ai) (optional) | A local image server for the paintings. Needs a GPU, about 12 GB of video memory |
| [Obsidian](https://obsidian.md) (optional) | To read your campaign between sessions |
| Chrome or Edge | To play at the table |

## Setting up

**1. Install.** Install [Claude Code](https://claude.com/claude-code) and log in (run `claude` once).
Then, in a terminal, in the folder where you want Ringwraith:

```sh
git clone <this repository's URL> ringwraith
cd ringwraith
python -m venv .venv
.venv/Scripts/activate                 # on Linux and macOS: source .venv/bin/activate
pip install -e .
copy ringwraith.example.toml ringwraith.toml    # cp on Linux and macOS
```

Open `ringwraith.toml` and set `vaults` to the folder where your campaigns should live. Every
`ringwraith` command below runs in this terminal, with the `.venv` activated.

**2. Add your books.** Put your PDFs in the `References` folder and check that they are recognised:

```sh
ringwraith doctor
```

They are recognised by the words in their file names, so they can be called anything that names the book
("Core Rules", "Strider Mode", "Moria"…). If one isn't, name it in `ringwraith.toml`; `doctor` shows how.

**3. Build the library.** Ringwraith doesn't read the PDFs during play. It reads a library of the rules,
tables, places and people, distilled from your books by Claude. This is done once, with Claude Code in the
`ringwraith` folder:

```sh
claude
```

and then, in Claude Code:

```
/distill
```

It extracts your books, then writes the library in `lore/` part by part, checking every table against the
page it came from. It's a long job, so it keeps its progress in `lore/DISTILL.md`. When a session runs out,
start a new one and type `/distill` again to continue where it stopped. You need only the rules (the first
five parts) to play. Places, adventures and the map of Eriador can wait until you want them.

Where the books leave a rule open, Claude writes its own ruling and marks it. At the end it goes through these
with you, and through the draft rules for leading a Band outside Moria if you play that way.

**4. Paintings (optional).** Install [Lemonade](https://lemonade-server.ai) and an image model as described
in [docs/art-models.md](docs/art-models.md), and leave it running while you play. `ringwraith doctor` shows
whether it is found. Without it, Ringwraith plays without pictures.

## Playing

```sh
ringwraith new bree-2965 --name "Shadows on the Greenway"   # a new campaign
ringwraith serve                                            # the table, at http://127.0.0.1:2965
```

In a new campaign, type `/session-zero` at the table: Ringwraith builds your hero and your Compass with
you, and sets the opening scene. After that, press **Begin session** to pick up where you left off and
**End session** when you stop; Ringwraith writes the session down and keeps the campaign in order.

Just say what your hero does. Ringwraith asks for rolls when the rules call for them. You can also type
`/paths` when you're unsure what to do next, `/hooks` for new adventures, `/oracle` to ask the world a
question, and `/steer` to point the tale somewhere ("/steer toward Angmar and the hill-men"): Ringwraith notes it
in your Compass and brings the story round to it through the world.

You decide how much Ringwraith decides. In **Settings** at the table you can read the oracles yourself
(Ringwraith suggests what an answer means; you accept it or say what it means instead) and turn off the Path
cards to come up with every choice on your own. Session zero asks about both, and about a premise for the
campaign, such as a published adventure you'd like to play through.

The table plays one campaign at a time. To play another, stop the table, switch, and start it again:

```sh
ringwraith campaigns                 # your campaigns (* = the active one)
ringwraith switch <name>
ringwraith easy on|off               # easy mode: easier fights
ringwraith dice-mode auto|manual     # dice rolled for you, or your own dice
ringwraith settings art.enabled false   # no paintings in this campaign
```

Each campaign is a folder in your `vaults` folder. Open it as a vault in Obsidian to read the tale so far:
the sessions, the people and places you've met, the threads still open and the maps.

The table is for one player on this computer. It listens only on `127.0.0.1` and refuses other web pages.

### The model and your plan

Ringwraith plays through your Claude login, so play counts against your plan's usage limits like any Claude
Code work. By default it uses Claude Code's default model for your account. To choose one for a campaign,
press **Settings** at the table (the same dialog sets the dice, easy mode, encounters and paintings); a new
model takes over from your next message. From the command line:

```sh
ringwraith settings table.model sonnet    # or opus, haiku, fable, or a full model id; restart ringwraith serve after
ringwraith settings table.model null      # back to the default
```

A Loremaster is a heavy user: every reply carries the rules card, the campaign and the conversation so far,
and a turn often makes several tool calls (rolls, notes, panels). Two things keep the cost down:

- **A fresh conversation each session.** The conversation's length, more than the model, sets the cost of
  each turn, because every turn rereads it: a conversation run over several sessions can cost several times as
  much per turn as a fresh one. So **Begin session** starts a new conversation whenever the last session was
  ended. Ringwraith remembers the campaign by the vault: a short story-so-far and the current scene in its
  hidden state, the last session's tale, the threads, the timeline and the notes on everyone met. A session
  you never ended (a reboot, a closed tab) keeps its conversation.
- **Pick the model for your plan.** Opus is the most faithful Loremaster; Sonnet costs much less per turn and
  lets a smaller plan play far longer. On the entry-level paid plan, expect Opus to reach the five-hour limit
  within a single evening's session; use Sonnet there, and watch your usage in Claude's settings.

## More

- [docs/development.md](docs/development.md): how Ringwraith is built, testing, and the screenshots
- [docs/roadmap.md](docs/roadmap.md): what works and what's next

## License

Ringwraith is released under the [MIT License](LICENSE). The bundled libraries in
`tools/ringwraith/web/static/vendor` keep their own licenses (see the README there).

Ringwraith is a fan project, not affiliated with Free League Publishing, Sophisticated Games or the Tolkien
Estate. The One Ring, Middle-earth and the names in it belong to their owners. You need the books to play.
