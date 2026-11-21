"""The demo campaign behind the README's screenshots: a short Moria tale played at the table.

`scripts/screenshots.py` builds it in a scratch vaults folder and runs the real table on it with Claude switched
off, then photographs the page. Each chapter is one stretch of play: what the player typed, what Ringwraith told,
and what its tools did (rolls, the fight, the journey, moves). The chapters run in order, so a shot of a later
chapter has the whole tale above it in the log, as a real session would.

To change a screenshot, edit its chapter or its entry in SHOTS and run `scripts/screenshots.py <name>`. The
paintings are in docs/screenshots/art/, made once with `scripts/screenshots.py --art` (local Lemonade).

Everything here is original writing for the demo. Rules text and numbers from the books never go in this file.
"""

HERO = "Edwy Rushworth"
COMPANY = [HERO, "Bryni Stonehelm", "Oswin Fernley", "Gytha"]
CAMPAIGN = {"slug": "the-long-dark", "name": "The Long Dark", "year": 2965}

# Paintings, made in the campaign's house style (book) with fixed seeds, so --art redraws the same pictures.
ART = {
    "pony": dict(preset="scene", mood="calm", time="dusk", seed=2965, subject=(
        "Inside the crowded common room of an old inn at Bree on a spring evening: low smoke-dark beams, a great "
        "stone fireplace with a roaring fire, Bree-folk and hobbits at long tables with mugs of ale and candles, "
        "a pot-boy with a tray. In a corner settle a stout Dwarf woman in a travel-stained blue hood sits across "
        "a small table from a young dark-haired Man in a brown cloak, a rolled parchment between them")),
    "hall": dict(preset="scene", mood="wonder", time="dawn", seed=2965, subject=(
        "The Twenty-first Hall of the North End, deep in Moria: a vast hall of the Dwarves under the mountain, a "
        "forest of tall carved stone pillars marching away into darkness, walls of polished black stone, the roof "
        "lost far overhead. A single long pale beam of morning light falls slantwise from a shaft high in the "
        "eastern wall and lies across the dusty floor. Broken bones and a rusted helm lie scattered on the "
        "flagstones. Tiny among the pillars, a small company of travellers with one shuttered lantern stands in "
        "the edge of the light, looking up")),
    "gate": dict(preset="scene", mood="battle", time="dusk", seed=535375114, subject=(
        "A wounded orc-chieftain in black iron mail roars and swings a notched scimitar, blood on his shoulder, "
        "planted on the threshold of a vast dark stone gateway; two orc archers behind him draw black-feathered "
        "arrows. Below on rocky steps outdoors a young man with a spear and a few grim companions hold the stair. "
        "The great east gate in a mountainside above a wild valley, grey cliffs, cold mist, red evening sky, "
        "shadowed doorway")),
    "falls": dict(preset="scene", mood="calm", time="dawn", seed=284635061, subject=(
        "Outdoors at dawn: a small travellers' camp beside a clear pool below a narrow waterfall in an ancient "
        "beech wood, grey bare boughs with swelling spring buds, mist rising off the water, a dying campfire, "
        "cloaked travellers stirring from their blankets, pale gold light through the trees, peaceful and quiet")),
    "edwy": dict(preset="portrait", mood="calm", seed=1101, subject=(
        "a young Man of Bree of about twenty-seven, dark untidy hair, a short dark beard, steady grey eyes, a "
        "weathered brown cloak over a mail shirt, a spear shaft over one shoulder")),
    "bryni": dict(preset="portrait", mood="calm", seed=1102, subject=(
        "a stout Dwarf woman of middle years, a thick braided red-brown beard bound with copper rings, a blue hood "
        "thrown back, keen dark eyes, a lantern-maker's leather apron under her travelling cloak")),
    "oswin": dict(preset="portrait", mood="calm", seed=1103, subject=(
        "a lean fair-haired Man of Bree in his thirties, clean-shaven, a crooked nose, a longbow over his "
        "shoulder, a green hood, a wry half-smile")),
    "gytha": dict(preset="portrait", mood="calm", seed=1104, subject=(
        "a grave Woodwoman of Mirkwood in her forties, grey-streaked black hair in a long plait, weathered face, "
        "a cloak of dyed green wool, sprigs of dried herbs tied at her belt")),
    "chieftain": dict(preset="adversary", mood="battle", time="dusk", seed=535375114, subject=(
        "an orc-chieftain in black iron mail with a notched scimitar, blood on one shoulder, roaring")),
    # A sketch in the tale: the hall as Bryni tells of it at the inn, long before the company sees it.
    "sketch-hall": dict(preset="sketch", seed=2965, subject=(
        "a vast hall of the Dwarves under the mountain, rows of tall carved stone pillars like tree trunks "
        "marching away into darkness, one pillar near the front marked with a small ring of runes, a single "
        "shaft of light falling from high above, no figures")),
}

HERO_SHEET = {
    "culture": "Men of Bree", "calling": "Treasure Hunter", "shadow_path": "Dragon-sickness", "age": 27,
    "patron": "Bryni Stonehelm's kin", "safe_haven": "Bree", "standard_of_living": "Common",
    "attributes": {"strength": 5, "heart": 4, "wits": 5},
    "endurance": {"max": 25, "current": 25}, "hope": {"max": 14, "current": 11},
    "shadow": {"points": 1, "scars": 0}, "fatigue": 0, "load": 14, "parry": 15,
    "valour": 2, "wisdom": 1, "fellowship": {"rating": 4, "current": 4},
    "xp": {"skill": 6, "adventure": 9},
    "skills": {
        "strength": {"awe": 1, "athletics": 2, "awareness": 2, "hunting": 1, "song": 0, "craft": 1},
        "heart": {"enhearten": 1, "travel": 2, "insight": 2, "healing": 0, "courtesy": 2, "battle": 2},
        "wits": {"persuade": 1, "stealth": 1, "scan": 2, "explore": 2, "riddle": 1, "lore": 0},
    },
    "favoured_skills": ["awareness", "explore", "insight"],
    "proficiencies": {"axes": 0, "bows": 1, "spears": 2, "swords": 1},
    "distinctive_features": ["Bold", "Fair-spoken"],
    "war_gear": [{"name": "Ash spear", "notes": "his father's"}, {"name": "Short sword"}],
    "armour": "Mail shirt",
}

BAND = {"readiness": 4, "burden": "medium",
        "dispositions": {"expertise": 2, "manoeuvre": 1, "rally": 2, "vigilance": 2, "war": 3},
        "shared_calling": "Treasure Hunters"}

ALLIES = {
    "Bryni Stonehelm": dict(art="bryni", culture="Dwarves of Durin's Folk",
                            gift="Deep-lore: reads old Dwarf-roads and door-marks by touch",
                            quirk="Talks to her lantern"),
    "Oswin Fernley": dict(art="oswin", culture="Men of Bree", gift="Sure shot: never wastes an arrow",
                          quirk="Bets on everything"),
    "Gytha": dict(art="gytha", culture="Woodmen of Wilderland", gift="Herb-wise: tends wounds on the road",
                  quirk="Will not sleep under stone"),
}

THREADS_OPEN = [
    "**Bryni's errand.** What did her grandfather's grandfather leave by the seventh pillar of the Twenty-first Hall?",
    "**The chieftain who fled.** He went back into the deep with the company's faces in his memory.",
]


# ---------------------------------------------------------------- the chapters

def pony(t):
    """Bree: Edwy meets Bryni at the inn. General roleplay, an Insight roll, Paths to choose from."""
    t.clock(day=3, time="night")
    t.scene("The Prancing Pony, a spring evening", art="pony")
    t.tell(
        "Rain has driven half of Bree indoors, and the common room of the Pony is loud with it: wet wool steaming by "
        "the fire, the clack of mugs, a hobbit at the long table trying to finish a song nobody wants to hear the "
        "end of. The landlord moves through it all with three jugs in each hand and an eye on everything.\n\n"
        "For the third night running the Dwarf in the blue hood has taken the corner settle. She orders one ale and "
        "makes it last. She doesn't drink much and she doesn't talk at all. She watches the door, and every time it "
        "opens, she looks at the face that comes in, and then, for a moment longer than she needs to, at you.\n\n"
        "At the next table Oswin Fernley has noticed too. He raises an eyebrow at you over his mug.\n\n"
        "What does Edwy do?")
    t.end_turn()

    t.player("I take my ale over to her corner and sit down without asking. \"Third night you've watched that "
             "door, mistress. Either you're waiting for someone, or you're waiting for someone to ask.\"")
    t.tell(
        "She doesn't startle. She looks at your mug, then at your hands, a long frank look as if she were pricing "
        "them, and only then at your face.\n\n"
        "\"Bryni,\" she says. \"Of the Stonehelms, who were lantern-makers in Khazad-dûm when your folk were still "
        "learning to thatch.\" There's no heat in it; she says it the way you'd give the weather. \"And I'm waiting "
        "for someone who has been somewhere dark and came back. The landlord says that's you. The barrow on the "
        "Downs, last autumn.\"\n\n"
        "From inside her coat she draws a roll of oiled cloth and lays it on the table between the candle and your "
        "ale. Charcoal rubbings: lines of angular runes, and below them the plan of a hall drawn as a field of "
        "dots, row on row, with one dot ringed twice.")
    t.sketch("The Twenty-first Hall, as Bryni tells it", "sketch-hall")
    t.tell(
        "\"The Twenty-first Hall of the North End. My grandfather's grandfather left something by the seventh "
        "pillar from the eastern arch, the night the Dwarves fled. I mean to bring it home.\" Her finger rests on "
        "the ringed dot. \"I need a few who don't run.\"\n\n"
        "What does Edwy do?")
    t.end_turn()

    t.player("Moria. She's actually asking me to walk into Moria. Before I say anything I want to know if she's "
             "telling me the whole of it. Can I read her?")
    t.tell("You let the noise of the room fill the silence and watch her while it does.", sep=True)
    t.roll("Edwy", "Insight", rating=2, tn=16, stakes="read whether Bryni is holding something back",
           feat=[8], success=[5, 6])
    t.tell(
        "She holds your eye, and she means every word. But when the door bangs open behind you, her hand goes flat "
        "on the cloth, covering the ringed dot, before she knows she has moved. It isn't greed in her face. It's "
        "fear, old and well-kept, the kind you carry for somebody else.\n\n"
        "\"You're wondering what it is,\" she says quietly. \"It's a debt. That's all you need to know until "
        "we're under the mountain, and then you'll have it all. My word on it.\"\n\n"
        "Oswin has given up pretending not to listen. He drags his stool over, sets his mug down next to the "
        "map, and grins at her. \"How dark is dark?\"\n\n"
        "> OOC:\n> - **Insight:** success (TN 16, total 19). She isn't lying, but there's a debt she won't name yet.")
    t.mark("inn")
    t.paths(["Shake on it tonight, and send word to Gytha in the Chetwood",
             "Sleep on it, and ask the landlord what he knows of the Stonehelms",
             "Ask Bryni to show you the whole rubbing by daylight, in the back parlour"])
    t.end_turn()


def gytha(t):
    """Back in Bree: Gytha won over in a council (the shot stops halfway, with the Council panel open)."""
    t.player("Shake on it tonight, and send word to Gytha in the Chetwood")
    t.tell(
        "You put out your hand. Bryni looks at it a moment, then takes it in a grip like a vice. Oswin slaps the "
        "table, and the hobbit at the long table loses his place in the song for good.\n\n"
        "The message to Gytha goes out with a carter at first light. Three days later she walks in out of the "
        "Chetwood with her pack on her back, hears the word *Moria* once, and sets the pack down by the door "
        "without opening it.\n\n"
        "\"No,\" she says. \"Not under the mountain. Not for a box I'm not allowed to see.\"\n\n"
        "> OOC:\n> - **The Band:** Bryni Stonehelm joins the company.\n"
        "> - **A council:** Gytha won't come unless she is persuaded.\n\nWhat does Edwy do?")
    t.end_turn()
    t.clock(day=6, time="dusk")

    t.player("I sit down across from her, not beside Bryni. I tell her what I saw in Bryni's face at the Pony, "
             "and that I wouldn't ask if I didn't think we'd need her hands down there.")
    t.council_start("Gytha's answer", ["Gytha"], "Come with us under the mountain", resistance=6,
                    attitude="unwilling")
    t.roll("Edwy", "Courtesy (introduction)", rating=2, tn=16, stakes="how long Gytha will hear him out",
           feat=[7], success=[4, 6])
    t.council_update(rounds=4, log="Edwy sits across from her, not beside Bryni.")
    t.tell(
        "Gytha doesn't look up from the knot she is picking at on her pack strap, but she stops picking at it.\n\n"
        "\"You saw her face,\" she says. \"So did I, when the carter said her name. That's a frightened woman, "
        "Edwy Rushworth. Frightened people lead you into places and then find they can't lead you out.\"\n\n"
        "> OOC:\n> - **Courtesy:** success (TN 16, total 17). She'll hear you out, for a while.\n\nWhat do you say?")
    t.end_turn()

    t.player("\"Then she needs someone who isn't frightened at her back. You've walked the Chetwood in the dark "
             "for twenty years. That's who I want.\"")
    t.roll("Edwy", "Persuade", rating=1, tn=15, stakes="win Gytha round", feat=[9], success=[6])
    t.council_update(used=1, add=2, attitude="listening", log="The Chetwood in the dark: she half smiles.")
    t.tell(
        "That gets the ghost of a smile. \"Twenty-two years,\" she says. \"And the Chetwood has a sky over it.\" "
        "But she has let go of the strap, and she is looking at Bryni now, not at the door.\n\n"
        "> OOC:\n> - **Persuade:** great success (TN 15, total 15, one {success}). She's listening.\n\n"
        "What does Edwy do?")
    t.end_turn()
    t.mark("council")

    t.player("I ask Bryni to tell her one true thing about the debt. Just one.")
    t.roll("Edwy", "Persuade (1d from Bryni)", rating=2, tn=15, stakes="win Gytha round", feat=[10], success=[6, 6])
    t.council_update(used=2, add=4, attitude="won over", log="Bryni tells her one true thing about the debt.")
    t.council_end("Gytha will come under the mountain.")
    t.tell(
        "Bryni looks at you a long moment. Then she leans across the table and says something to Gytha so low "
        "that you only catch the word *grandfather*.\n\n"
        "Gytha closes her eyes. When she opens them she reaches for the pack by the door, unbuckles it, and starts "
        "sorting her herbs.\n\n"
        "> OOC:\n> - **Persuade:** extraordinary success. **Gytha comes.** The council counts as a Fellowship "
        "milestone.\n> - **A new thread:** Bryni's errand.\n\nThe road east is long. Where do you begin?")
    t.end_turn()


def hall(t):
    """Under the mountain: the Twenty-first Hall, an oracle question, and a roll waiting in the tray."""
    t.player("We go by the Redhorn road and come in by the West-gate, as Bryni says. Three days in the dark, then "
             "the hall.")
    t.place(COMPANY, "Doors of Durin", day=23)
    t.move(COMPANY, "Dwarrowhall", day=26)
    t.clock(day=26, time="dawn")
    t.sheet(hope=8, fatigue=2, eye=7)
    t.scene("The Twenty-first Hall", art="hall")
    t.tell(
        "Three days with no sky. Three days of stairs that go down when they should go up, of halls so wide your "
        "lantern finds neither wall, of Bryni's voice counting under her breath, always counting. Gytha has not "
        "spoken since the second night.\n\n"
        "Then, on the fourth morning, there is light. Grey, thin, impossible: a single beam falling slantwise from "
        "some shaft far up in the eastern wall, lying across the dust like a fallen spear. In it you can see the "
        "pillars at last, row on row of them, carved like the trunks of trees, marching away into a dark that has "
        "no end.\n\n"
        "Bryni stops. Her hand is shaking on the lantern. \"The Twenty-first Hall,\" she whispers. \"Seven from "
        "the eastern arch.\"\n\n"
        "Oswin lets out a breath. \"Well. It's real, then.\"\n\nWhat does Edwy do?")
    t.end_turn()
    t.mark("view")

    t.player("\"Lamps shuttered. Oswin, watch the arches.\" I walk the line of pillars beside Bryni with my spear "
             "low, keeping to the edge of the light.")
    t.oracle("Is the company being followed?", "likely", feat=9, answer="Yes")
    t.tell(
        "Seven pillars. The seventh is no different from the rest until Bryni sets her palm flat on it, and then "
        "you see it: a seam, finer than a hair, running up the stone in the shape of a narrow door. She says "
        "something in her own tongue, very softly, the way you'd speak to a sleeping child.\n\n"
        "Behind you, far off in the dark of the northern arch, a pebble falls.\n\n"
        "It bounces twice and rolls, and then there is nothing. No footstep. No breath. Only the long silence of "
        "the mountain, which is somehow fuller than it was a moment ago.\n\n"
        "Oswin's bowstring creaks. Gytha has her hand on her knife. Nobody looks round.\n\n"
        "> OOC:\n> - **The Telling** (likely): yes, something has followed you.\n\nWhat does Edwy do?")
    t.end_turn()

    t.player("I don't turn round. I let my eyes drift to the shadows behind the pillars and I listen, the way you "
             "listen for a fox at the hen-house.")
    t.tell("You stand very still in the edge of the light and give the dark your whole attention.", sep=True)
    t.ask_roll("Edwy", "Awareness", rating=2, tn=15, favoured=True,
               stakes="see what is moving among the pillars before it reaches the light, or be taken by surprise")


def gate(t):
    """The Dimrill Gate: a Band battle against the orcs that followed the company out of the deep."""
    t.answer_roll(feat=[7, 10], success=[4, 6], hope=False)
    t.tell(
        "There: two pillars back and one to the left, where the light doesn't reach. A shape that is not a shadow, "
        "because shadows don't breathe. Then another. Then the gleam of a blade, low down, held by someone who "
        "has done this before.\n\n"
        "\"Orcs,\" you say, quite calmly. \"Behind us, in the northern arch. Bryni, open your door or leave it. "
        "Now.\"\n\n"
        "> OOC:\n> - **Awareness:** success (TN 15, total 17). You see them first: no surprise.")
    t.end_turn()
    t.player("Whatever she takes out of the door, we run for the East-gate. Two days, if Bryni's right.")
    t.move(COMPANY, "East-gate of Moria", day=28)
    t.clock(day=28, time="dusk")
    t.sheet(endurance=21, hope=7, fatigue=3, eye=9)
    t.scene("The Dimrill Gate", art="gate")
    t.fight_start("battle", "The orcs at the Dimrill Gate", stance="forward", foes=[
        dict(name="Orc-chieftain", endurance=18, hate=4, features=["Cruel", "Proud"], weapons=["Notched scimitar"],
             engaged=["Edwy"]),
        dict(name="Orc archers", count=4, endurance=7, hate=1, weapons=["Black-feathered arrows"]),
        dict(name="Orc soldiers", count=9, endurance=9, hate=1, weapons=["Spears", "Jagged knives"]),
    ], battle=dict(clash=1, resistance=24, objective="Win the Dimrill Stair and the open sky",
                   objective_resistance=12, advantages=["The light at your backs"],
                   complications=["Tired from the long run"], focus="Edwy leads from the front",
                   band_stance="forward"))
    t.tell(
        "Light. Real light, red and gold, pouring in through the Gate ahead of you, and the smell of snow and "
        "grass after two days of stone. You come up the last stair at a run, and the Dimrill Dale opens beneath "
        "you, wide and wild under the evening sky.\n\n"
        "And on the threshold, between you and all of it, stands the chieftain.\n\n"
        "He is bigger than any orc you've seen, black-mailed, a notched scimitar in his fist. Two archers draw "
        "behind him. From the dark at your backs comes the rush of feet, the rest of them, the ones who followed "
        "you from the hall. He has been waiting. He grins, and says something in his own tongue that makes the "
        "archers laugh.\n\n"
        "> OOC:\n> - **A battle begins.** Your objective: win the Stair and the open sky.\n"
        "> - The Band fights in a forward stance, with you at its head.\n\nWhat does Edwy do?")
    t.end_turn()

    t.player("\"Bryni, Gytha, hold the stair behind us. Oswin, the archers.\" I lower my spear and go straight "
             "at him. We go through him, not round him.")
    t.roll("Edwy", "Battle (Clash)", rating=2, tn=16, stakes="break the chieftain's hold on the Gate",
           feat=[10], success=[6, 4])
    t.roll("Orc-chieftain", "Clash", rating=3, tn=14, adversary=True, feat=["eye"], success=[2, 5, 1])
    t.fight_update(round=2, foes=[dict(name="Orc-chieftain", endurance=11, wounded=True),
                                  dict(name="Orc archers", down=2),
                                  dict(name="Orc soldiers", down=3)],
                   battle=dict(clash=2, resistance=13, objective_resistance=7))
    t.tell(
        "You hit the chieftain like a thrown stone. Your spear takes him high in the shoulder, through the mail, "
        "and the grin is gone. He swings at you, but the swing has no weight behind it, and the notched blade "
        "rings off the rock beside your head.\n\n"
        "Oswin's first arrow takes an archer in the throat. His second goes wide, and he swears, and his third "
        "doesn't. Behind you, on the stair, Bryni's axe is a sound you will not forget: a short flat chop, again "
        "and again, and Gytha's voice under it, low and steady, calling the next one.\n\n"
        "The chieftain gives a step. Then another. Black blood runs down his arm, and for the first time he looks "
        "past you, at the dark of the Gate behind him.\n\n"
        "> OOC:\n> - **Clash:** great success for you (TN 16, total 20); the chieftain's attack failed.\n"
        "> - **The chieftain** is Wounded. Two archers and three soldiers are down.\n"
        "> - The stair is yielding.\n\nThe chieftain backs onto the threshold, blood on his shoulder. What does "
        "Edwy do?")
    t.end_turn()


def journey(t):
    """The road down the Silverlode to Caras Galadhon: the Journey panel, its interludes and a cutaway."""
    t.player("He's beaten. Let him go. We hold the Gate until first light.")
    t.fight_end("The chieftain flees into the dark of Moria; the Gate is held.")
    t.tell(
        "The chieftain doesn't wait to hear what you've decided. One moment he is on the threshold, blood on his "
        "teeth; the next the dark of the Gate has swallowed him, and only the slap of his feet on old stone comes "
        "back, fainter and fainter, until there's nothing.\n\n"
        "You hold the Gate through the rest of the night. No more come. When the sky over the Dimrill Dale turns "
        "from black to grey, the mist lifts off Mirrormere and the long valley opens below you, green and silent, "
        "falling away east towards the far gold haze of the Golden Wood.\n\n"
        "> CUTAWAY: Far below, in a hall where no light has fallen for a thousand years, the chieftain crawls the "
        "last steps on his hands. Beyond the pillars something waits in the dark. It hears his gasping tale of a "
        "gate held against them, and of folk who make for the Golden Wood. A voice older than orc-speech answers "
        "him with a single word, and far off in the deep a drum begins to beat.\n\n"
        "> OOC:\n> - **The battle is won.** The chieftain is gone, Wounded, into the deep.\n\nWhat does Edwy do?")
    t.end_turn()

    t.player("We don't stay to hear that drum. Down the Stair, and follow the Silverlode to the Golden Wood. "
             "Gytha says her people trade with the Elves there.")
    t.journey_start("East-gate of Moria", "Caras Galadhon", title="The Gate to Caras Galadhon", season="spring")
    t.clock(day=29, time="day")
    t.journey_log(dict(kind="march", title="Down the Dimrill Stair to Mirrormere", at="Mirrormere", hexes_done=1),
                  "The old stair is broken, but it is still a stair, and Dwarf-hands made it to last. You go down it in "
                  "the morning chill, step by worn step, with the Gate shrinking to a dark mouth behind you. By noon "
                  "you stand on the shore of Mirrormere. The water lies long and still between the mountains, so dark "
                  "and clear that the peaks stand upside down in it.\n\n"
                  "Bryni walks to the edge and kneels there a long time, and none of you go near her.\n\n"
                  "> OOC:\n> - **The road:** 1 of 3 hexes behind you, on the old road.", move_to="Mirrormere")
    t.clock(day=29, time="night")
    t.journey_log(dict(kind="interlude", title="The camp by Mirrormere",
                       text="Bryni opens her grandfather's box at last, and tells the company what the debt was."),
                  "You make camp where the stream leaves the lake, with a low fire and your backs to a boulder. When "
                  "the others have eaten, Bryni sets the thing from the pillar on her knees: a small iron box, "
                  "black with age, no bigger than a loaf.\n\n"
                  "\"A promise,\" she says, \"is a debt. He promised to bring the lamp-maker's book out to his son, "
                  "and he died on the stair with it still in the wall.\" She opens the lid. Inside, wrapped in oiled "
                  "silk, a book of thin bronze leaves. \"Now it's paid.\"\n\n"
                  "Nobody says anything for a long while. Then Oswin raises his cup to the dark water, and after a "
                  "moment so do you.")
    t.clock(day=30, time="day")
    t.journey_log(dict(kind="event", title="A hard crossing at the Nimrodel", at="Falls of Nimrodel", who="the Band",
                       outcome="across, soaked and bruised", hexes_done=2, fatigue_hero=1, fatigue_band=1),
                  "The second day goes well until the Nimrodel. The stream comes down out of the west in a rush of "
                  "white water, swollen with the spring melt, and the old stepping stones are a hand's breadth under "
                  "the flood. You cross roped together, the cold so sharp it makes your teeth ache. Halfway over a "
                  "stone turns under Oswin's foot and the line goes taut; for a long moment you all hang on the rope "
                  "in the roaring water. Then you are over, gasping on the far bank, every pack soaked.\n\n"
                  "> OOC:\n> - **Event (the Band):** a hard crossing. Fatigue +1 for you and for the Band.\n"
                  "> - **The road:** 2 of 3 hexes behind you.", move_to="Falls of Nimrodel")
    t.clock(day=30, time="night")
    t.journey_log(dict(kind="interlude", title="The camp below the Falls",
                       text="Oswin asks why Edwy let the chieftain go."),
                  "You camp below the falls, where the noise of the water fills the night so completely that it is "
                  "almost a kind of silence. Wet clothes steam by the fire. Somewhere above, in the dark trees, a "
                  "voice is singing, high and far off, in a tongue none of you knows; or perhaps it is only the "
                  "water.\n\n"
                  "Oswin has been quiet all day. Now, turning a boot to the fire, he speaks.\n\n"
                  "\"I keep thinking about the Gate. You had him. One more thrust and he'd never have told anyone "
                  "anything.\" He looks at you across the flames, not angry, only wanting to understand. \"Why did "
                  "you let him go?\"\n\nWhat does Edwy say?", end=True)

    t.player("I'm quiet for a long time. \"Because he was done, Oz. And because I'd have been the one going back "
             "into the dark after him, with you lot behind me.\" I poke the fire. \"Maybe that was wrong. Ask me "
             "again when we hear that drum closer.\"")
    t.clock(day=31, time="dawn")
    t.sheet(fatigue=4, endurance=23)
    t.scene("Dawn below the Falls of Nimrodel", art="falls")
    t.tell(
        "Oswin doesn't answer at once. He turns the boot over, looks at the steam coming off it, and nods slowly, "
        "as if you've told him the price of something and he's decided it's fair.\n\n"
        "\"Closer,\" he says. \"Right. I'll hold you to that.\"\n\n"
        "Gytha, who you'd thought asleep, says without opening her eyes: \"You were right to.\" And that is the "
        "end of it.\n\n"
        "In the morning the mist lies on the pool like milk, and the beech-boughs are grey and bare and full of "
        "buds. The singing has stopped. But on a flat stone by the water, where none of you set it, someone has "
        "left a little loaf wrapped in a leaf, and beside it a single grey feather.\n\n"
        "> CUTAWAY: Two days behind you, the Dimrill Gate stands open to the dawn. On its threshold the "
        "chieftain's blood has dried black. Something steps over it without looking down: tall, wrapped in rags, "
        "its feet bare on the cold stone. It lifts its head to the east wind and breathes in, slowly, the smell "
        "of the Golden Wood.\n\n"
        "> OOC:\n> - **Fellowship:** the talk at the fire restores 1 Fellowship point.\n"
        "> - **The road:** 1 hex to Caras Galadhon.\n\nWhat does Edwy do?")
    t.end_turn()


CHAPTERS = [pony, gytha, hall, gate, journey]

# name: upto (the last chapter played), at (stop at that chapter's t.mark), view (scene or map), steps (JavaScript
# run in the page before the shot, in order), size (the window, default 1920x1200).
SHOTS = {
    "inn": dict(upto="pony", at="inn",
                # up to the sketch without tucking the stage away, as scrolling by hand would
                steps=["ignoreScrollUntil = performance.now() + 5000; "
                       "logEl.scrollTop += document.querySelector('figure.sketch').getBoundingClientRect().top "
                       "- logEl.getBoundingClientRect().top - 20"],
                caption="Roleplay at the inn: the painted scene, the tale, and a sketch of the hall Bryni tells of"),
    "paths": dict(upto="pony", caption="Paths: a few ways forward as cards, or anything else you type"),
    "view": dict(upto="hall", at="view", steps=["document.getElementById('stage').click()"],
                 caption="Taking in the view: click the painting to see all of it"),
    "council": dict(upto="gytha", at="council",
                    caption="Councils: the Council panel shows how far they are swayed and the exchanges left"),
    "roll": dict(upto="hall", caption="Under the mountain: the dice tray shows the odds with and without Hope"),
    "battle": dict(upto="gate", caption="A Band battle at the Gate: the Fight panel shows what the hero can see"),
    "journey": dict(upto="journey", steps=["document.getElementById('log').scrollBy(0, -170)"],
                    caption="The road to Lórien: the Journey panel, the camps on the way, and a cutaway"),
    "map": dict(upto="journey", view="map", caption="The map of the tale: the road so far and who is where"),
    "tale": dict(upto="journey", steps=["document.getElementById('dtab-tale').click()"],
                 caption="The Tale: the journey under way, open threads and the Compass"),
}
