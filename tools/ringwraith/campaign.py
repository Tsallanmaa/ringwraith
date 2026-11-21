"""Campaign selection and per-campaign settings.

Each campaign is its own Obsidian vault under <vaults>/<slug>/. Ringwraith's
private files live in the vault's hidden `.ringwraith/` folder (Obsidian does
not show dot-folders). The active campaign's slug is stored in <vaults>/.active.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

from . import config as cfg

DEFAULTS: dict[str, Any] = {
    "difficulty": {
        # Easy mode (web/prompt.md, Fights). Band campaigns: hero TN = 18 - Attribute, Band TN = 18 - Readiness,
        # and the hero gains the Strider Distinctive Feature. Off = 20 - Attribute, no Strider
        # (a Strider Mode campaign has both anyway: tn_base).
        "easy": False,
        # story = fights sized and resolved to keep the tale going (web/prompt.md, Fights);
        # standard = by the book.
        "encounters": "story",
    },
    "dice": {"mode": "auto"},          # auto = scripted rolls, manual = player rolls physical dice
    # style: book | classic. lora: an optional style LoRA and its named looks (docs/art-models.md).
    "art": {"enabled": True, "model": None, "max_per_session": 20, "style": "book", "lora": None},
    # oracle: who reads the oracles shown at the table, loremaster or player (Ringwraith suggests, the player
    # decides). paths: show Path cards (offer_paths); off, the player makes every choice unprompted.
    "play": {"oracle": "loremaster", "paths": True},
    "table": {"model": None},          # the Loremaster's model (opus, sonnet, a model id); None = Claude Code's default
}


class CampaignError(RuntimeError):
    pass


def vaults_root(c: cfg.Config | None = None) -> Path:
    return (c or cfg.load()).vaults


def active_slug(root: Path | None = None) -> str | None:
    """The active campaign: $RINGWRAITH_CAMPAIGN if set (e.g. by `serve --campaign`), else the .active file."""
    if os.environ.get("RINGWRAITH_CAMPAIGN"):
        return os.environ["RINGWRAITH_CAMPAIGN"]
    f = (root or vaults_root()) / ".active"
    return f.read_text(encoding="utf-8").strip() or None if f.exists() else None


def set_active(slug: str, root: Path | None = None) -> None:
    root = root or vaults_root()
    if not (root / slug).is_dir():
        raise CampaignError(f"no campaign vault {root / slug}")
    from . import fileio
    fileio.atomic_write(root / ".active", slug + "\n")


def campaign_dir(slug: str | None = None, root: Path | None = None) -> Path:
    root = root or vaults_root()
    slug = slug or active_slug(root)
    if not slug:
        raise CampaignError("no active campaign (create one with `ringwraith new`)")
    d = root / slug
    if not d.is_dir():
        raise CampaignError(f"campaign vault not found: {d}")
    return d


def private_dir(slug: str | None = None, root: Path | None = None) -> Path:
    d = campaign_dir(slug, root) / ".ringwraith"
    d.mkdir(exist_ok=True)
    return d


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_settings(slug: str | None = None, root: Path | None = None) -> dict:
    f = private_dir(slug, root) / "settings.yaml"
    data = yaml.safe_load(f.read_text(encoding="utf-8")) if f.exists() else {}
    return _merge(DEFAULTS, data or {})


def save_settings(settings: dict, slug: str | None = None, root: Path | None = None) -> Path:
    from . import fileio
    f = private_dir(slug, root) / "settings.yaml"
    fileio.atomic_write(f, yaml.safe_dump(settings, sort_keys=False, allow_unicode=True))
    return f


def set_value(dotted: str, value: Any, slug: str | None = None, root: Path | None = None) -> dict:
    from . import fileio
    with fileio.locked():
        return _set_value(dotted, value, slug, root)


def _set_value(dotted: str, value: Any, slug: str | None, root: Path | None) -> dict:
    s = load_settings(slug, root)
    node = s
    *parents, leaf = dotted.split(".")
    for p in parents:
        node = node.setdefault(p, {})
    node[leaf] = value
    save_settings(s, slug, root)
    return s


# ------------------------------------------------------------- rules hooks

def _strider(settings: dict) -> bool:
    """A lone hero (Strider Mode) plays at 18 - Attribute with the Strider feature, by the book. In a Band campaign
    those come only with easy mode."""
    return (settings.get("campaign") or {}).get("mode") == "strider"


def tn_base(settings: dict) -> int:
    return 18 if settings["difficulty"]["easy"] or _strider(settings) else 20


def hero_tn(attribute: int, settings: dict) -> int:
    return tn_base(settings) - attribute


def has_strider_feature(settings: dict) -> bool:
    return bool(settings["difficulty"]["easy"]) or _strider(settings)
