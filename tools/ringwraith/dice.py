"""The One Ring 2e dice.

Feat die (d12): 1-10, the Eye of Sauron (11, counts as 0) and the Gandalf rune
(12, automatic success). Success dice (d6): 1-6, the 6 also shows a success
icon. A test rolls one Feat die plus N Success dice against a TN.

Rules implemented (core pp.16-22):
  * Favoured: roll two Feat dice, keep the best. Ill-favoured: keep the worst.
    Both at once cancel out to a normal roll.
  * gain (Nd) / lose (Nd) add or remove Success dice (minimum 0).
  * Hope: spend 1 point (max once per roll) to gain (1d), or (2d) if Inspired.
  * Weary: Success dice showing 1-3 count as 0.
  * Miserable: an {eye} on the Feat die is an automatic failure.
  * Degree: success, great (1 icon), extraordinary (2+ icons).
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field

EYE = "eye"
GANDALF = "gandalf"
FEAT_FACES: list[int | str] = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, EYE, GANDALF]

_rng: random.Random = random.SystemRandom()


def seed(value: int | None) -> None:
    """Make rolls reproducible (tests); None restores the system RNG."""
    global _rng
    _rng = random.SystemRandom() if value is None else random.Random(value)


def parse_feat(token: str | int) -> int | str:
    t = str(token).strip().lower()
    if t in ("eye", "e", "11", "{eye}"):
        return EYE
    if t in ("gandalf", "g", "12", "rune", "{gandalf}"):
        return GANDALF
    n = int(t)
    if not 1 <= n <= 10:
        raise ValueError(f"feat die value must be 1-10, eye or gandalf, not {token!r}")
    return n


def feat_rank(face: int | str) -> int:
    """Ordering for keeping best/worst: eye < 1 < ... < 10 < gandalf."""
    return 0 if face == EYE else 11 if face == GANDALF else int(face)


def feat_value(face: int | str) -> int:
    """Numeric contribution to the total. The rune succeeds anyway; it adds 10 for display."""
    return 0 if face == EYE else 10 if face == GANDALF else int(face)


def roll_feat_face() -> int | str:
    return FEAT_FACES[_rng.randrange(12)]


def roll_success_face() -> int:
    return _rng.randint(1, 6)


def feat_mode(favoured: bool, ill: bool) -> str:
    if favoured and not ill:
        return "favoured"
    if ill and not favoured:
        return "ill-favoured"
    return "normal"


def as_hero(face: int | str, adversary: bool) -> int | str:
    """Adversaries read the Feat die the Shadow's way: {eye} is their best result, {gandalf} is 0."""
    if not adversary:
        return face
    return GANDALF if face == EYE else EYE if face == GANDALF else face


def pick_feat(faces: list[int | str], mode: str, adversary: bool = False) -> int | str:
    key = lambda f: feat_rank(as_hero(f, adversary))  # noqa: E731
    if mode == "favoured":
        return max(faces, key=key)
    if mode == "ill-favoured":
        return min(faces, key=key)
    return faces[0]


@dataclass
class TestResult:
    dice: int                      # Success dice actually rolled
    mode: str                      # normal | favoured | ill-favoured
    feat_rolled: list = field(default_factory=list)
    feat: int | str = 0
    success: list[int] = field(default_factory=list)
    weary: bool = False
    miserable: bool = False
    tn: int | None = None
    total: int = 0
    icons: int = 0
    outcome: str = ""              # success | failure | rolled (no TN)
    degree: str = ""               # success | great | extraordinary | ""
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def test(
    rating: int,
    tn: int | None = None,
    *,
    favoured: bool = False,
    ill: bool = False,
    bonus: int = 0,
    penalty: int = 0,
    hope: bool = False,
    inspired: bool = False,
    weary: bool = False,
    miserable: bool = False,
    adversary: bool = False,
    feat: list[int | str] | None = None,
    success: list[int] | None = None,
) -> TestResult:
    """Roll (or evaluate given dice for) a TOR test.

    `feat` / `success` supply physical-dice results instead of rolling.
    `adversary` swaps the icons: {eye} succeeds automatically, {gandalf} counts as 0.
    """
    hope_dice = (2 if inspired else 1) if hope else 0
    n = max(0, rating + bonus + hope_dice - penalty)
    mode = feat_mode(favoured, ill)
    r = TestResult(dice=n, mode=mode, weary=weary, miserable=miserable, tn=tn)
    if hope:
        r.notes.append(f"Hope spent: gain ({hope_dice}d)")

    need = 1 if mode == "normal" else 2
    if feat is None:
        r.feat_rolled = [roll_feat_face() for _ in range(need)]
    else:
        faces = [parse_feat(f) for f in feat]
        if len(faces) != need:
            raise ValueError(f"{mode} roll needs {need} Feat die result(s), got {len(faces)}")
        r.feat_rolled = faces
    r.feat = pick_feat(r.feat_rolled, mode, adversary)
    eff = as_hero(r.feat, adversary)

    if success is None:
        r.success = [roll_success_face() for _ in range(n)]
    else:
        if len(success) != n:
            raise ValueError(f"expected {n} Success die result(s), got {len(success)}")
        if any(not 1 <= s <= 6 for s in success):
            raise ValueError("Success dice show 1-6")
        r.success = list(success)

    counted = [0 if (weary and s <= 3) else s for s in r.success]
    r.icons = sum(1 for s in r.success if s == 6)
    r.total = feat_value(eff) + sum(counted)
    if weary and any(s <= 3 for s in r.success):
        r.notes.append("Weary: 1-3 on Success dice count as 0")

    if tn is None:
        r.outcome = "rolled"
    elif miserable and not adversary and r.feat == EYE:
        r.outcome = "failure"
        r.notes.append("Miserable: {eye} is an automatic failure")
    elif eff == GANDALF:
        r.outcome = "success"
        r.notes.append("{eye}: automatic success for the adversary" if adversary
                       else "{gandalf}: automatic success")
    else:
        r.outcome = "success" if r.total >= tn else "failure"

    if r.outcome == "success":
        r.degree = "extraordinary" if r.icons >= 2 else "great" if r.icons == 1 else "success"
    return r


@dataclass
class Odds:
    dice: int
    success: float          # P(success), any degree
    great: float            # P(success with exactly 1 icon)
    extraordinary: float    # P(success with 2+ icons)


def _feat_distribution(mode: str, adversary: bool) -> dict[int | str, float]:
    """Probability of each kept Feat face (as the roller reads it) for normal/favoured/ill rolls."""
    faces = sorted((as_hero(f, adversary) for f in FEAT_FACES), key=feat_rank)
    dist: dict[int | str, float] = {}
    for i, f in enumerate(faces):           # i faces rank below f, 11 - i rank above
        if mode == "favoured":
            p = ((i + 1) ** 2 - i ** 2) / 144
        elif mode == "ill-favoured":
            p = ((12 - i) ** 2 - (11 - i) ** 2) / 144
        else:
            p = 1 / 12
        dist[f] = p
    return dist


def _success_distribution(n: int, weary: bool) -> dict[tuple[int, int], float]:
    """Probability of (sum, icons) over n Success dice."""
    dist = {(0, 0): 1.0}
    for _ in range(n):
        nxt: dict[tuple[int, int], float] = {}
        for (s, k), p in dist.items():
            for v in range(1, 7):
                key = (s + (0 if weary and v <= 3 else v), k + (v == 6))
                nxt[key] = nxt.get(key, 0.0) + p / 6
        dist = nxt
    return dist


def odds(rating: int, tn: int, *, favoured: bool = False, ill: bool = False, bonus: int = 0,
         penalty: int = 0, hope: bool = False, inspired: bool = False, weary: bool = False,
         miserable: bool = False, adversary: bool = False) -> Odds:
    """Exact chances of a test, using the same rules as test()."""
    n = max(0, rating + bonus + ((2 if inspired else 1) if hope else 0) - penalty)
    succ = _success_distribution(n, weary)
    total = great = extra = 0.0
    for face, pf in _feat_distribution(feat_mode(favoured, ill), adversary).items():
        if miserable and not adversary and face == EYE:
            continue
        auto = face == GANDALF
        for (s, k), ps in succ.items():
            if auto or feat_value(face) + s >= tn:
                p = pf * ps
                total += p
                if k == 1:
                    great += p
                elif k >= 2:
                    extra += p
    return Odds(n, total, great, extra)


def describe_odds(rating: int, tn: int, **kw) -> str:
    """Chances without Hope, with Hope, and (if not already Inspired) with Hope while Inspired."""
    kw = {k: v for k, v in kw.items() if k != "hope"}
    rows = [("no Hope", odds(rating, tn, **kw)),
            ("spend Hope" + (" (Inspired, +2d)" if kw.get("inspired") else " (+1d)"),
             odds(rating, tn, hope=True, **kw))]
    if not kw.get("inspired"):
        rows.append(("Hope + Inspired (+2d)", odds(rating, tn, hope=True, **{**kw, "inspired": True})))
    mode = feat_mode(kw.get("favoured", False), kw.get("ill", False))
    flags = [f for f in ("weary", "miserable") if kw.get(f)]
    head = f"Odds: TN {tn}, {mode}" + (", " + ", ".join(flags) if flags else "")
    lines = [head]
    for name, o in rows:
        lines.append(f"  {name:24} {o.dice}d  success {o.success:4.0%}  "
                     f"(great {o.great:3.0%}, extraordinary {o.extraordinary:3.0%})")
    return "\n".join(lines)


def face_str(face: int | str) -> str:
    return "{eye}" if face == EYE else "{gandalf}" if face == GANDALF else str(face)


def describe(r: TestResult) -> str:
    feat = face_str(r.feat)
    if len(r.feat_rolled) > 1:
        feat += f" ({r.mode}: {', '.join(face_str(f) for f in r.feat_rolled)})"
    succ = " ".join(("{success}" if s == 6 else str(s)) for s in r.success) or "-"
    head = f"Feat {feat} | Success [{succ}] | total {r.total}"
    if r.tn is not None:
        verdict = r.outcome.upper()
        if r.degree in ("great", "extraordinary"):
            verdict += f" ({r.degree}, {r.icons} icon{'s' if r.icons != 1 else ''})"
        head += f" vs TN {r.tn} -> {verdict}"
    if r.notes:
        head += "\n  " + "; ".join(r.notes)
    return head
