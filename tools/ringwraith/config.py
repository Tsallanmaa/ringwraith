"""Machine-local configuration (ringwraith.toml at the repo root)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = REPO_ROOT / "ringwraith.toml"
EXAMPLE_FILE = REPO_ROOT / "ringwraith.example.toml"

KEYS = ("references", "build", "lore", "vaults")   # [paths]; every one must be set, there are no defaults


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    references: Path
    build: Path
    lore: Path
    vaults: Path
    lemonade_url: str
    loaded_from: Path | None


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def load(config_file: Path = CONFIG_FILE) -> Config:
    """The settings in ringwraith.toml. Nothing is assumed: a missing file or setting is an error that says what
    to set."""
    if not config_file.exists():
        raise ConfigError(f"no {config_file.name}: copy {EXAMPLE_FILE.name} to {config_file.name} and set its paths")
    with config_file.open("rb") as fh:
        data = tomllib.load(fh)
    paths = data.get("paths", {})
    missing = [k for k in KEYS if not paths.get(k)]
    if missing:
        raise ConfigError(f"{config_file.name}: set {', '.join(missing)} under [paths]")
    url = data.get("lemonade", {}).get("url", "")
    return Config(
        references=_resolve(paths["references"]),
        build=_resolve(paths["build"]),
        lore=_resolve(paths["lore"]),
        vaults=_resolve(paths["vaults"]),
        lemonade_url=url.rstrip("/"),
        loaded_from=config_file,
    )
