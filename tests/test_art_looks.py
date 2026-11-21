"""Sketches and style-LoRA looks: the prompts, the extra-args block sd-server reads, and the queue's checks."""

import json
import re

import pytest

from ringwraith import art, artqueue
from ringwraith import campaign as cp


def _settings(tmp_path, file=True):
    f = tmp_path / "style.safetensors"
    if file:
        f.write_bytes(b"x")
    return {"lora": {"file": str(f), "strength": 0.6, "looks": {
        "painted": {"words": "zz painting.", "house_style": True, "when": "quiet scenes"},
        "bright": {"words": "zz illustration.", "house_style": False, "strength": 0.9, "when": "warm scenes"},
        "sketch": {"words": "zz illustration."}}}}


def test_a_sketch_has_its_own_pencil_look_and_no_house_style():
    p = art.build_prompt("sketch", "the tower on the hill", "dread", "night")
    assert p.endswith(art.SKETCH_STYLE) and "the tower on the hill" in p
    assert art.BOOK_BASE not in p and "nocturne" not in p


def test_looks_lead_the_prompt_and_keep_or_drop_the_house_style(tmp_path):
    s = _settings(tmp_path)
    painted, bright = art.find_look(s, "painted"), art.find_look(s, "bright")
    assert painted.strength == 0.6 and bright.strength == 0.9          # the look's own strength wins
    p = art.build_prompt("scene", "two friends over maps", "calm", "day", look=painted)
    assert p.startswith("zz painting. ") and art.BOOK_BASE in p
    p = art.build_prompt("scene", "two friends over maps", "calm", "day", look=bright)
    assert p.startswith("zz illustration. ") and art.BOOK_BASE not in p and art.MOODS["calm"] in p
    assert p.endswith(art.SETTING)
    sk = art.build_prompt("sketch", "an old bridge", look=art.find_look(s, "sketch"))
    assert sk.startswith("zz illustration. ") and sk.endswith(art.SKETCH_STYLE)


def test_unknown_looks_and_missing_files_are_refused(tmp_path):
    assert art.find_look({}, None) is None
    with pytest.raises(art.ArtError, match="no style LoRA"):
        art.find_look({"lora": None}, "painted")
    with pytest.raises(art.ArtError, match="looks: painted, bright, sketch"):
        art.find_look(_settings(tmp_path), "gloomy")
    with pytest.raises(art.ArtError, match="absolute path"):
        art.find_look(_settings(tmp_path / "elsewhere", file=False), "painted")
    s = _settings(tmp_path)
    s["lora"]["file"] = "style.safetensors"                              # relative: sd-server wouldn't find it
    with pytest.raises(art.ArtError, match="absolute path"):
        art.find_look(s, "painted")


def test_the_lora_block_carries_everything_sd_server_needs(tmp_path):
    look = art.find_look(_settings(tmp_path), "painted")
    payload = {"seed": 7, "negative_prompt": art.NEGATIVE, "steps": 9, "cfg_scale": 1.0}
    block = art.lora_args(payload, look)
    extra = json.loads(re.fullmatch(r"<sd_cpp_extra_args>(.*)</sd_cpp_extra_args>", block).group(1))
    assert extra == {"seed": 7, "negative_prompt": art.NEGATIVE,
                     "lora": [{"path": look.file, "multiplier": 0.6}],
                     "sample_params": {"sample_steps": 9, "guidance": {"txt_cfg": 1.0}}}


def test_the_queue_checks_the_look_and_a_look_skips_portrait_references(tmp_path):
    (tmp_path / "camp").mkdir()
    cp.set_active("camp", tmp_path)
    with pytest.raises(art.ArtError):
        artqueue.enqueue("scene", "a hall", root=tmp_path, look="painted")
    cp.set_value("art.lora", _settings(tmp_path)["lora"], root=tmp_path)
    job = artqueue.enqueue("scene", "a hall", root=tmp_path, look="painted", characters=["Sid"])
    assert job["look"] == "painted"
    assert artqueue.job_refs(tmp_path / "camp", job, root=tmp_path) == []
    sk = artqueue.enqueue("sketch", "an old bridge", root=tmp_path)
    assert sk["file"].startswith("90 Assets/sketches/")


def test_the_worker_uses_the_sketch_look_and_falls_back_to_the_house_style(tmp_path):
    s, said = _settings(tmp_path), []
    assert artqueue._look(s, {"preset": "sketch"}, True, said.append).name == "sketch"
    assert artqueue._look(s, {"preset": "scene"}, True, said.append) is None
    assert artqueue._look(s, {"preset": "scene", "look": "bright"}, False, said.append) is None   # fallback model
    assert artqueue._look({"lora": None}, {"preset": "sketch"}, True, said.append) is None       # no LoRA: plain
    assert artqueue._look(s, {"preset": "scene", "look": "gone"}, True, said.append) is None
    assert said and "gone" in said[-1]


def test_the_looks_reach_the_loremasters_instructions_without_the_sketch(tmp_path, monkeypatch):
    from ringwraith.web import engine
    monkeypatch.setattr(cp, "load_settings", lambda *a, **k: {"art": _settings(tmp_path)})
    text = engine.looks_section()
    assert "`painted`: quiet scenes" in text and "`bright`: warm scenes" in text and "`sketch`" not in text
    monkeypatch.setattr(cp, "load_settings", lambda *a, **k: {"art": {"lora": None}})
    assert engine.looks_section() == ""


def test_badly_written_lora_settings_are_refused_plainly(tmp_path):
    s = _settings(tmp_path)
    s["lora"]["looks"]["odd"] = "zz painting."                      # a look written as a string
    s["lora"]["looks"]["loud"] = {"words": "zz", "strength": "strong"}
    s["lora"]["looks"]["plain"] = {"words": "zz", "house_style": "no"}
    for name in ("odd", "loud"):
        with pytest.raises(art.ArtError):
            art.find_look(s, name)
    assert art.find_look(s, "plain").house_style is False
    assert art.look_names({"lora": {"file": "x", "looks": ["a", "b"]}}) == {}


def test_a_sketch_is_never_painted_from_portraits(tmp_path):
    assert artqueue.job_refs(tmp_path, {"preset": "sketch", "characters": ["Sid"]}) == []
