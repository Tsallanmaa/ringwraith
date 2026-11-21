"""Telling story from bookkeeping in what the Loremaster writes at the table.

The model writes free text between tool calls. The engine uses these checks to show its own working notes
("Writing up Fitch and Cob…") faintly instead of as story, to notice a reply that gives only the dice, and to
move mechanics that drifted into the story paragraphs into the OOC box. They are heuristics on plain text:
pure functions, no state, tested in tests/test_web.py.
"""

from __future__ import annotations

import re

# Text the model writes between tool calls is sometimes its own bookkeeping ("Writing up Fitch and
# Cob, then the scene..."). Such asides are shown as a faint working note, not as story.
PLAYER_FACING = {"request_roll", "roll_adversary", "ask", "roll_table", "set_scene", "offer_paths", "fight", "journey"}
ASIDE_START = re.compile(
    r"^(let me|let's|i'll|i will|i'm going|i am going|i need|i've|now (i|let)|next,? i|first,? i|"
    r"writing|updating|checking|recording|saving|noting|creating|adding|looking|reading|loading|"
    r"logging|filing|drafting|wrapping up|queueing|queuing|"
    r"setting up|rolling for|consulting|opening|sorting|one moment|bear with me)\b", re.I)
PLACEHOLDER = re.compile(r"\b(?:the |a )?(?:story|scene|tale|narration) (?:follows|to follow|comes next|is coming)\b|"
                         r"\b(?:back|more) (?:in a moment|shortly)\b", re.I)


BOOKKEEPING_WORDS = re.compile(
    r"\b(note|notes|sheet|sheets|vault|frontmatter|session note|threads|timeline|state file|"
    r"write[- ]?up|bookkeeping|portrait|queue)\b", re.I)


def ends_with_question(text: str) -> bool:
    """Does the story end by handing the scene back to the player ("What does Tomas do?")."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip() and not l.strip().startswith(">")]
    return bool(lines) and lines[-1].rstrip("*_ ").endswith("?")


MECHANICS = re.compile(
    r"\bTN\s*\d|\bagainst TN\b|\{(?:gandalf|eye|success)\}|\bEye Awareness\b|\bTelling table\b|"
    r"(?-i:\b[A-Z]{4,} (?:roll|test)\b)|\broll(?:ed)?,? (?:came|was|is|gave|failed|succeeded)\b|"
    r"\b(?:great|extraordinary) success\b|\bfeat die\b", re.I)


def is_mechanics_only(text: str) -> bool:
    """A reply that opens with the dice ("The INSIGHT roll came to 14 against TN 16...") rather than story."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip() and not p.strip().startswith(">")]
    return bool(paras) and MECHANICS.search(paras[0]) is not None


TALK_OF_MECHANICS = re.compile(
    r"\boracles?\b|\b(?:certain|likely|middling|doubtful|unthinkable) odds\b|"
    r"\b\d+ (?:Endurance|Hope|Fatigue|Shadow|Eye Awareness)\b|\bday \d+\b", re.I)


def _mechanical(para: str) -> bool:
    """Mechanics in a story paragraph. A paragraph with dialogue in it is story ("We ride on day 3," says Sid;
    "the oracle at the well"): only the strong signs (a TN, dice icons, "the INSIGHT roll") count there."""
    if MECHANICS.search(para):
        return True
    return not any(q in para for q in '"“”') and TALK_OF_MECHANICS.search(para) is not None


def tidy_story(text: str) -> tuple[str, bool]:
    """Move mechanics that drifted into the story paragraphs ("The oracle question was…, and it came up a 1",
    "Tomas has 24 Endurance, 4 Hope") into the OOC box before the closing question. The opening paragraph
    stays where it is (a reply that opens with the dice is handled by the retell). Returns (text, moved)."""
    paras = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if len(paras) < 3:
        return text, False
    end = len(paras)
    while end > 1 and paras[end - 1].strip() == "---":
        end -= 1
    last = paras[end - 1].strip()
    closing = not last.startswith(">") and (ends_with_question(last) or (len(last) < 160 and "\n" not in last))
    q = end - 1 if closing else end
    story, moved, box = [paras[0]], [], None
    for p in paras[1:q]:
        s = p.strip()
        if s.startswith(">") and not re.match(r">\s*OOC:", s, re.I):
            story.append(p)                       # another quote (a cutaway, verse, a letter) is part of the tale
        elif s.startswith(">"):
            box = s if box is None else box + "\n>\n" + s
        elif s == "---":
            continue
        elif _mechanical(s):
            moved.append(s)
        else:
            story.append(p)
    if not moved:
        return text, False
    lines = [("> " + l if l.strip() else ">") for m in moved for l in (m.splitlines() + [""])][:-1]
    extra = "\n".join(lines)
    if box is None:
        box = "> OOC:\n" + extra
    else:
        box = box + "\n>\n" + extra
    return "\n\n".join(story + [box] + paras[q:]), True


RETELL = ("(The table, not the player.) The player hasn't seen what happened after the last roll or oracle: your "
          "reply gave only the mechanics, and your thinking is hidden from them. Write that scene now as the "
          "storyteller: a few prose paragraphs of what the hero sees and hears, with the speakers' own words, "
          "so the outcome is lived through. No mechanics, no summary, no question and no Paths: your summary and "
          "question are already on the table and the story goes above them.")


def is_aside(text: str, next_tool: str | None) -> bool:
    t = text.strip()
    if not t or t.startswith(">") or "\n\n" in t or len(t) > 220 or any(q in t for q in '"“”'):
        return False
    if ASIDE_START.match(t) or PLACEHOLDER.search(t):
        return True
    return (next_tool is not None and next_tool not in PLAYER_FACING
            and BOOKKEEPING_WORDS.search(t) is not None)
