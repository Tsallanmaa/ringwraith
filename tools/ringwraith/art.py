"""Image generation through a local Lemonade server.

Every image is saved as PNG with a sidecar JSON (prompt, model, seed, size,
timing), so any picture can be reproduced or regenerated with a better model.
"""

from __future__ import annotations

import base64
import io
import json
import math
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# The look of The One Ring 2e books: painterly, muted, earthy, grounded realism.
STYLE = (
    "traditional oil painting on canvas, visible brush strokes, impasto texture, "
    "in the manner of a 19th-century academic painter, "
    "muted earthy palette of ochre, umber, moss green and slate, "
    "Middle-earth, Third Age, grounded realism, no text"
)
# Mood replaces the gentle default light and atmosphere, so a fight doesn't look like a picnic.
MOODS: dict[str, str] = {
    "calm": "soft natural light, melancholic and hopeful mood",
    "wonder": "luminous golden light, awe and quiet wonder, sense of ancient beauty",
    "tense": "suspense, held breath, danger close at hand, deep shadows, wary watchful eyes, something is wrong",
    "danger": "threatening atmosphere, menace in every shadow, harsh contrasting light, imminent peril",
    "battle": "violent struggle frozen mid-action, snarling bared fangs and raised weapons, "
              "dynamic diagonal composition, motion and chaos, dramatic chiaroscuro firelight, mortal peril",
    "dread": "oppressive darkness, cold sickly light, overwhelming fear and despair, sorcery in the air",
    "sorrow": "grey muted light, grief and loss, stillness, rain",
}
DEFAULT_MOOD = {"adversary": "danger"}

# Time of day goes at the very start of the prompt (the model weighs the start most); night also
# swaps the house style for candlelit darkness, and gets a colour grade after painting.
TIMES: dict[str, str] = {
    "dawn": "at dawn, cold pale early light, long low shadows, mist",
    "day": "in daylight",
    "dusk": "at dusk, the last red-gold light fading, long shadows, the dark gathering",
    "night": "a nocturne at dead of night, near-total darkness, the only light a small flame or thin moonlight",
}
NIGHT_STYLE = (
    "traditional oil painting on canvas, visible brush strokes, tenebrism in the manner of Rembrandt and "
    "Georges de La Tour, most of the canvas in deep blue-black darkness, warm golden highlights only where "
    "flame or moonlight falls, Middle-earth, Third Age, grounded realism, no text"
)


# The house styles a campaign can choose (settings: art.style). "book": the look of the modern One Ring books
# (misty, cool, painterly), the default. "classic": a 19th-century academic oil painting. No artist is named.
BOOK_BASE = ("atmospheric painterly digital illustration in the manner of modern tabletop fantasy book art, "
             "loose expressive brushwork with soft edges, muted cool palette of teal, slate blue and grey-green, "
             "deep soft shadows, one warm glowing light source against the gloom")
BOOK_OUTDOOR = ("misty atmospheric perspective, the land and sky large and deep around the figures, distance "
                "fading into haze")
BOOK_INDOOR = ("an enclosed interior: walls, beams and ceiling close around the figures, smoky air, no open sky, "
               "no landscape, no view outside")
BOOK_NIGHT = ("a nocturne, most of the picture in deep blue-black darkness and cool teal shadow, warm light only "
              "where flame or moonlight falls")
BOOK_RUIN = ("abandoned and decaying, cold grey-blue light, dust hanging thick in the still air, rubble, "
             "cobwebs and broken stone, most of the scene lost in deep darkness, light only in narrow shafts and "
             "small pools, no soft fill light, desolate and silent")
BOOK_UNDERGROUND = ("halls carved from the living rock deep under the mountain, no windows, no buildings, daylight "
                    "only as a thin shaft through a narrow opening cut in the stone far above, bare rough-hewn rock "
                    "walls whose only carvings are rows of angular Dwarf-runes and square geometric knotwork")
BOOK_DARKWOOD = ("an ancient dark forest pressing close, huge gnarled trunks and twisting roots, branches leaning in "
                 "overhead, no sky, a heavy green-grey gloom under the canopy, still air, the trees themselves "
                 "watchful and hostile")
STYLES = ("book", "classic")
DEFAULT_STYLE = "book"
_INTERIOR = re.compile(r"\b(room|rooms|hall|chamber|attic|cellar|parlou?r|common room|inn|tavern|kitchen|office|"
                       r"study|library|shop|counting-house|inside|interior|indoors|under the eaves|beneath the rafters|"
                       r"rafters|staircase|stairs|desk|hearth|tent|barn|stable|smithy|workshop|crypt|vault|cave|cavern|"
                       r"mine|mansion|throne)\b", re.I)
_EXTERIOR = re.compile(r"\b(outside|outdoors|open sky|on the road|in the yard|yard|lane|street|on the step|doorstep|"
                       r"before (?:a|an|the) [a-z -]{0,40}(?:house|cottage|gate|door|hall|tower|inn)|on the hill|"
                       r"under the stars|in the fields?|in the woods?|forest|riverbank|ford|bridge|hillside|moor)\b",
                       re.I)


_RUIN = re.compile(r"\b(moria|khazad-d[uû]m|dwarrowdelf|mines?|ruins?|ruined|crumbling|abandoned|deserted|"
                   r"derelict|forsaken|desolate|barrows?|barrow-downs|tombs?|crypts?|catacombs?|haunted|decay|"
                   r"decaying|cobwebs?|broken bones|fallen (?:city|hall|tower|halls)|dead city)\b", re.I)


_UNDERGROUND = re.compile(r"\b(moria|khazad-d[uû]m|dwarrowdelf|mazarbul|under the mountain|beneath the mountain|"
                          r"deep under|underground|mines?|caves?|cavern|tunnels?|delvings?|dwarf-halls?)\b", re.I)
_DARKWOOD = re.compile(r"\b(old forest|withywindle|old man willow|mirkwood|fangorn|taur-nu-fuin|eryn vorn|haunted wood|dark wood)\b", re.I)


def is_underground(subject: str) -> bool:
    return bool(_UNDERGROUND.search(subject))


def is_darkwood(subject: str) -> bool:
    return bool(_DARKWOOD.search(subject))


def is_ruin(subject: str) -> bool:
    """A ruined, abandoned or haunted place (Moria, barrows, old towers): colder, dustier, darker."""
    return bool(_RUIN.search(subject))


def is_interior(subject: str) -> bool:
    """Does the picture happen indoors? (So the style keeps the walls round it.)"""
    head = subject                                # the first place word in the description decides
    inside, outside = _INTERIOR.search(head), _EXTERIOR.search(head)
    if inside and outside:                        # both: whichever the description names first
        return inside.start() < outside.start()
    return bool(inside)


def style_text(style: str, time: str | None, interior: bool, ruin: bool = False, underground: bool = False,
               darkwood: bool = False) -> str:
    if style == "classic":
        return NIGHT_STYLE if time == "night" else STYLE
    if darkwood and not underground:           # a dark forest has its own close, living gloom
        parts = [BOOK_BASE, BOOK_DARKWOOD]
    else:
        parts = [BOOK_BASE, BOOK_INDOOR if interior or underground else BOOK_OUTDOOR]
    if underground:
        parts.append(BOOK_UNDERGROUND)
    if ruin:
        parts.append(BOOK_RUIN)
    if time == "night":
        parts.append(BOOK_NIGHT)
    return ", ".join(parts) + ", Middle-earth, Third Age, no text"


def time_from_text(text: str | None) -> str | None:
    """Map a free-text time of day (from the state clock) to one of TIMES."""
    t = (text or "").lower()
    if not t:
        return None
    if any(w in t for w in ("dusk", "evening", "sunset", "twilight", "nightfall")):
        return "dusk"
    if any(w in t for w in ("night", "midnight", "small hours", "dark")):
        return "night"
    if any(w in t for w in ("dawn", "sunrise", "daybreak", "first light")):
        return "dawn"
    return "day"


def grade(img: Image.Image, time: str | None, ruin: bool = False, darkwood: bool = False) -> Image.Image:
    """Colour grade for night and dusk: darker, cooler shadows, flame-lit highlights kept warm, vignette.
    A ruin also gets less colour, colder greys and deeper shadow, whatever the hour."""
    if ruin:
        img = _ruin_grade(img)
    elif darkwood:
        img = _ruin_grade(img, tint=(0.86, 0.96, 0.84))
    if time not in ("night", "dusk"):
        return img
    import numpy as np
    a = np.asarray(img.convert("RGB")).astype(np.float32) / 255.0
    lum = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    if time == "night":
        tint, gamma, edge, floor = np.array([0.6, 0.66, 0.88]), 1.2, 0.5, 0.35
    else:
        tint, gamma, edge, floor = np.array([0.92, 0.82, 0.78]), 1.08, 0.35, 0.55
    warm = np.clip((lum - 0.55) / 0.35, 0, 1)[..., None]
    out = (a * tint) * (1 - warm) + a * warm
    out = out ** gamma
    h, w = lum.shape
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    out *= np.clip(1.12 - edge * r ** 1.6, floor, 1)[..., None]
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))
def _ruin_grade(img: Image.Image, tint=(0.84, 0.92, 1.0)) -> Image.Image:
    """Cold, dusty and dim: colour drained toward grey-blue, midtones and edges darkened, bright light kept."""
    import numpy as np
    a = np.asarray(img.convert("RGB")).astype(np.float32) / 255.0
    lum = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    grey = lum[..., None]
    a = a * 0.6 + grey * 0.4                                     # less colour
    keep = np.clip((lum - 0.62) / 0.3, 0, 1)[..., None]           # lanterns and shafts of light stay bright
    cold = a * np.array(tint) * (1 - keep) + a * keep
    cold = cold ** 1.18                                            # deeper shadow, less fill
    h, w = lum.shape
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    cold *= np.clip(1.1 - 0.42 * r ** 1.7, 0.45, 1)[..., None]
    return Image.fromarray((np.clip(cold, 0, 1) * 255).astype(np.uint8))


DEFAULT_MODEL = "Z-Image-Turbo-Q8B"   # custom Lemonade model, see docs/art-models.md
FALLBACK_MODEL = "Flux-2-Klein-4B"
REF_MODEL = "Flux-2-Klein-4B"         # paints scenes from portrait references (consistent faces)
UPSCALER = "RealESRGAN-x4plus"
EDIT_MAX_PIXELS = 400_000             # larger edits run out of memory on a 12 GB card
REF_MAX_SIDE = 512                    # a face needs no more; smaller references leave room for the picture
MAX_REFS = 3
UPSCALE_BLEND = 0.4                   # share of the RealESRGAN result in the final picture
NEGATIVE = "text, watermark, signature, logo, modern clothing, plastic, cartoon, anime, oversaturated, extra fingers"


@dataclass(frozen=True)
class Preset:
    size: tuple[int, int]
    template: str


PRESETS: dict[str, Preset] = {
    "portrait": Preset((768, 1024), "head-and-shoulders portrait of {subject}, detailed face, plain painterly background"),
    "scenery": Preset((1024, 640), "wide landscape view of {subject}, sense of distance and weather"),
    "adversary": Preset((768, 1024), "menacing {subject}, full figure, dark and dangerous, lit by firelight or moonlight. Tolkien-style goblin-orc, ashen grey and sallow skin, squat and bow-legged, long arms, wearing scavenged black mail"),
    "item": Preset((768, 768), "{subject}, an object study on a dark wooden table, finely detailed craftsmanship"),
    "scene": Preset((1344, 576), "{subject}, wide cinematic composition, figures fully in frame with their heads "
                                 "well below the top edge, characters in their surroundings"),
    # A small drawing in the tale of something told or heard, not seen: its own pencil look, never the house style.
    "sketch": Preset((768, 512), "{subject}"),
}
SETTING = "Middle-earth, Third Age, pre-industrial, no text"
SKETCH_STYLE = ("pencil and ink drawing on aged parchment, fine cross-hatching, sepia and graphite tones, "
                "monochrome, loose sketchy linework, hand-drawn book illustration, no text")


@dataclass(frozen=True)
class Look:
    """A named look from a style LoRA (settings: art.lora). `words` lead the prompt (usually the LoRA's trigger);
    with house_style the rest of the prompt is the usual one, without it only the subject, mood and time."""
    name: str
    words: str
    house_style: bool
    file: str
    strength: float


def look_names(art_settings: dict) -> dict[str, str]:
    """The configured looks and when to use them: {name: when}. Empty without a LoRA."""
    lora = art_settings.get("lora") or {}
    if not isinstance(lora, dict) or not lora.get("file"):
        return {}
    looks = lora.get("looks") or {}
    if not isinstance(looks, dict):
        return {}
    return {str(n): str(v.get("when") or "") if isinstance(v, dict) else "" for n, v in looks.items()}


def find_look(art_settings: dict, name: str | None) -> Look | None:
    """The named look, or None when none is asked for. A sketch uses the look named 'sketch' if there is one.
    Raises ArtError for an unknown look or a missing LoRA file."""
    if not name:
        return None
    lora = art_settings.get("lora") or {}
    looks = look_names(art_settings)
    if name not in looks:
        raise ArtError(f"no look {name!r}" + (f"; looks: {', '.join(looks)}" if looks else
                                             " (no style LoRA is set up in art.lora)"))
    f = Path(str(lora["file"])).expanduser()
    if not f.is_absolute() or not f.is_file():
        raise ArtError(f"art.lora.file must be the absolute path of an existing file: {f}")
    v = lora["looks"][name]
    if not isinstance(v, dict):
        raise ArtError(f"art.lora.looks.{name} must be a mapping (words, house_style, when, strength)")
    try:
        strength = float(v.get("strength", lora.get("strength", 1.0)))
    except (TypeError, ValueError):
        raise ArtError(f"art.lora strength for {name!r} must be a number") from None
    house = v.get("house_style", True)
    if isinstance(house, str):             # a quoted "no" or "false" in hand-written YAML
        house = house.strip().lower() not in ("no", "false", "off", "0")
    return Look(name, str(v.get("words") or "").strip(), bool(house), str(f), strength)


@dataclass
class ArtResult:
    path: str
    model: str
    preset: str
    subject: str
    prompt: str
    seed: int
    size: str
    seconds: float


class ArtError(RuntimeError):
    pass


class Unreachable(ArtError):
    """The image server isn't answering (not started, or restarting): the job itself is fine, so try it later."""


def build_prompt(preset: str, subject: str, mood: str | None = None, time: str | None = None,
                 style: str | None = None, look: Look | None = None) -> str:
    if preset not in PRESETS:
        raise ArtError(f"unknown preset {preset!r}; choose from {', '.join(PRESETS)}")
    mood = (mood or DEFAULT_MOOD.get(preset, "calm")).lower()
    if mood not in MOODS:
        raise ArtError(f"unknown mood {mood!r}; choose from {', '.join(MOODS)}")
    if time is not None and time not in TIMES:
        raise ArtError(f"unknown time of day {time!r}; choose from {', '.join(TIMES)}")
    style = style or DEFAULT_STYLE
    if style not in STYLES:
        raise ArtError(f"unknown art style {style!r}; choose from {', '.join(STYLES)}")
    lead = ", ".join(x for x in (TIMES.get(time or "") if time != "day" else "", MOODS[mood]) if x)
    interior = is_interior(subject)
    template = PRESETS[preset].template
    if interior and preset == "scenery":          # a room is not a landscape
        template = "interior view of {subject}, the room close around"
    body = template.format(subject=subject.rstrip('. '))
    words = f"{look.words} " if look and look.words else ""
    if preset == "sketch":
        return f"{words}{body}, {SKETCH_STYLE}"
    if look and not look.house_style:
        return f"{words}{lead}: {body}, {SETTING}"       # the style goes, the setting stays (no modern tents)
    return f"{words}{lead}: {body}, {style_text(style, time, interior, is_ruin(subject), is_underground(subject), is_darkwood(subject))}"


def _post(url: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise ArtError(f"Lemonade {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from e
    except urllib.error.URLError as e:
        raise Unreachable(f"Lemonade not reachable at {url}: {e.reason}") from e


def image_models(base_url: str) -> list[dict]:
    with urllib.request.urlopen(f"{base_url}/api/v1/models", timeout=5) as r:
        data = json.load(r).get("data", [])
    return [m for m in data
            if "image" in (m.get("labels") or []) or m.get("recipe") == "sd-cpp"]


# Generation settings for models that don't carry Lemonade defaults (custom user.* models).
MODEL_PARAMS: dict[str, dict] = {
    "Z-Image-Turbo-Q8B": {"steps": 9, "cfg_scale": 1.0},
    "user.Z-Image-Turbo-Q8B": {"steps": 9, "cfg_scale": 1.0},
}


def free_vram_for(base_url: str, model: str, log=print) -> list[str]:
    """Unload other image-generation models Lemonade keeps loaded (they hold GPU memory)."""
    try:
        with urllib.request.urlopen(f"{base_url}/api/v1/health", timeout=5) as r:
            loaded = json.load(r).get("all_models_loaded", [])
    except (urllib.error.URLError, ValueError):
        return []
    freed = []
    for m in loaded:
        name = m.get("model_name")
        if name and name != model and "sd-cpp" in str(m.get("launch_command", "")) + str(m.get("recipe", "")):
            try:
                _post(f"{base_url}/api/v1/unload", {"model_name": name}, 30)
                freed.append(name)
                log(f"unloaded {name} to free GPU memory")
            except ArtError as e:
                log(f"could not unload {name}: {e}")
    return freed


def lora_args(payload: dict, look: Look) -> str:
    """sd-server's request options with a LoRA, to append to the prompt. sd-server reads only the first such block
    and Lemonade sends seed, steps, cfg and negative prompt in a block of its own after the prompt, so this one
    must carry them all. The LoRA path must be absolute."""
    extra = {"seed": payload["seed"], "negative_prompt": payload["negative_prompt"],
             "lora": [{"path": look.file, "multiplier": look.strength}]}
    params = {}
    if payload.get("steps"):
        params["sample_steps"] = payload["steps"]
    if payload.get("cfg_scale") is not None:
        params["guidance"] = {"txt_cfg": payload["cfg_scale"]}
    if params:
        extra["sample_params"] = params
    return f"<sd_cpp_extra_args>{json.dumps(extra)}</sd_cpp_extra_args>"


def generate(base_url: str, model: str, prompt: str, size: tuple[int, int], seed: int | None = None,
             steps: int | None = None, timeout: float = 600, look: Look | None = None) -> tuple[Image.Image, int, float]:
    seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    payload = {"model": model, "prompt": prompt, "negative_prompt": NEGATIVE,
               "size": f"{size[0]}x{size[1]}", "n": 1, "response_format": "b64_json", "seed": seed}
    payload.update(MODEL_PARAMS.get(model, {}))
    if steps:
        payload["steps"] = steps
    if look:
        payload["prompt"] = prompt + lora_args(payload, look)
    t0 = time.perf_counter()
    try:
        data = _post(f"{base_url}/api/v1/images/generations", payload, timeout)
    except ArtError as e:
        if "returned no results" not in str(e):
            raise
        # sd-server sometimes gets stuck after an image; reloading the model clears it.
        try:
            _post(f"{base_url}/api/v1/unload", {"model_name": model}, 60)
        except ArtError:
            pass
        data = _post(f"{base_url}/api/v1/images/generations", payload, timeout)
    secs = time.perf_counter() - t0
    try:
        img = Image.open(io.BytesIO(base64.b64decode(data["data"][0]["b64_json"])))
    except (KeyError, IndexError) as e:
        raise ArtError(f"unexpected Lemonade response: {str(data)[:300]}") from e
    return img.convert("RGB"), seed, secs


def _multipart(fields: dict, files: list[tuple[str, str, bytes]]) -> tuple[bytes, str]:
    import uuid
    boundary = uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for name, filename, data in files:
        out.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
                   f"Content-Type: image/png\r\n\r\n".encode() + data + b"\r\n")
    return b"".join(out) + f"--{boundary}--\r\n".encode(), boundary


def edit_size(size: tuple[int, int]) -> tuple[int, int]:
    """The largest size with the same shape that fits an edit in memory (multiples of 64)."""
    w, h = size
    k = min(1.0, math.sqrt(EDIT_MAX_PIXELS / (w * h)))
    return max(256, int(w * k) // 64 * 64), max(256, int(h * k) // 64 * 64)


def edit(base_url: str, model: str, prompt: str, refs: list[Path], size: tuple[int, int], seed: int | None = None,
         timeout: float = 600) -> tuple[Image.Image, int, float]:
    """Paint from reference images (Flux-style editing): the references keep faces and clothing consistent."""
    seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    files = []
    for f in refs[:MAX_REFS]:
        im = Image.open(f).convert("RGB")
        im.thumbnail((REF_MAX_SIDE, REF_MAX_SIDE))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        files.append(("image[]", Path(f).name, buf.getvalue()))
    fields = {"model": model, "prompt": prompt, "size": f"{size[0]}x{size[1]}", "n": 1, "response_format": "b64_json",
              "seed": seed}
    body, boundary = _multipart(fields, files)
    req = urllib.request.Request(f"{base_url}/api/v1/images/edits", data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    t0 = time.perf_counter()
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:300]
            if attempt == 2 or "no results" not in msg:
                raise ArtError(f"Lemonade {e.code}: {msg}") from e
            time.sleep(3)       # usually the model is still loading
        except urllib.error.URLError as e:
            raise Unreachable(f"Lemonade not reachable: {e.reason}") from e
    img = Image.open(io.BytesIO(base64.b64decode(data["data"][0]["b64_json"]))).convert("RGB")
    return img, seed, time.perf_counter() - t0


def upscale(base_url: str, img: Image.Image, target: tuple[int, int], model: str = UPSCALER) -> Image.Image:
    """RealESRGAN x4, then down to the target size: sharp detail from a small edit."""
    buf = io.BytesIO()
    img.save(buf, "PNG")
    data = _post(f"{base_url}/api/v1/images/upscale",
                 {"image": base64.b64encode(buf.getvalue()).decode(), "model": model}, 600)
    up = Image.open(io.BytesIO(base64.b64decode(data["data"][0]["b64_json"]))).convert("RGB")
    return up.resize(target, Image.LANCZOS)


def ref_intro(names: list[str]) -> str:
    """Tell the model which reference image is whom."""
    if not names:
        return ""
    parts = [f"image {i + 1} shows {n}" for i, n in enumerate(names[:MAX_REFS])]
    return ("Reference images: " + "; ".join(parts) + ". Paint each of them with exactly the face, hair and "
            "clothing of their reference image. ")


def render_with_refs(base_url: str, preset: str, subject: str, refs: list[tuple[str, Path]], out: Path,
                     seed: int | None = None, mood: str | None = None, time_: str | None = None,
                     model: str = REF_MODEL, style: str | None = None) -> "ArtResult":
    """A picture of known characters: painted from their portraits, then upscaled and graded."""
    names = [n for n, _ in refs]
    prompt = build_prompt(preset, ref_intro(names) + subject, mood, time_, style)
    size = PRESETS[preset].size
    small = edit_size(size)
    img, seed, secs = edit(base_url, model, prompt, [f for _, f in refs], small, seed)
    t0 = time.perf_counter()
    plain = img.resize(size, Image.LANCZOS)        # keeps the brush texture
    try:                                           # RealESRGAN adds crisp edges but smooths paint: blend
        img = Image.blend(plain, upscale(base_url, img, size), UPSCALE_BLEND)
    except ArtError:
        img = plain                                # upscaler missing: the plain resize is fine
    secs += time.perf_counter() - t0
    img = grade(img, time_, is_ruin(subject), is_darkwood(subject))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    res = ArtResult(str(out), model, preset, subject, prompt, seed, f"{size[0]}x{size[1]}", round(secs, 1))
    meta = {**asdict(res), "refs": names, "edit_size": f"{small[0]}x{small[1]}"}
    out.with_suffix(".json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return res


def render(base_url: str, model: str, preset: str, subject: str, out: Path,
           seed: int | None = None, steps: int | None = None, mood: str | None = None,
           time: str | None = None, style: str | None = None, look: Look | None = None) -> ArtResult:
    prompt = build_prompt(preset, subject, mood, time, style, look)
    size = PRESETS[preset].size
    img, seed, secs = generate(base_url, model, prompt, size, seed, steps, look=look)
    if preset != "sketch" and look is None:      # the grade belongs to the house style; a look brings its own light
        img = grade(img, time, is_ruin(subject), is_darkwood(subject))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    res = ArtResult(str(out), model, preset, subject, prompt, seed, f"{size[0]}x{size[1]}", round(secs, 1))
    meta = asdict(res) | ({"look": look.name, "lora_strength": look.strength} if look else {})
    out.with_suffix(".json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return res


# ---------------------------------------------------------------- shootout

SHOOTOUT = [
    ("portrait", "a weathered Man of Bree in his forties, brown wool cloak, short beard, kind wary eyes"),
    ("portrait", "a young Hobbit woman of the Shire with curly auburn hair, green waistcoat, holding a walking stick"),
    ("adversary", "an Orc of the Misty Mountains with a notched scimitar and crude iron armour"),
    ("scenery", "the village of Bree at dusk under Bree-hill, thatched roofs, a hedge and dike around it, lights in windows"),
    ("scenery", "the ruined watchtower on Weathertop under a stormy sky, grey grass slopes"),
    ("item", "an ancient long dagger of Westernesse with a leaf-shaped blade and red-gold runes on the hilt"),
]


def shootout(base_url: str, models: list[str], out_dir: Path, seed: int = 2965,
             log=print) -> list[ArtResult]:
    results: list[ArtResult] = []
    for model in models:
        log(f"== {model} (first image includes model load time)")
        free_vram_for(base_url, model, log=log)
        for i, (preset, subject) in enumerate(SHOOTOUT, 1):
            path = out_dir / model / f"{i:02d}-{preset}.png"
            try:
                r = render(base_url, model, preset, subject, path, seed=seed)
                results.append(r)
                log(f"   {i}. {preset:9} {r.seconds:6.1f}s  {path.name}")
            except ArtError as e:
                log(f"   {i}. {preset:9} FAILED: {e}")
    if results:
        sheet = contact_sheet(results, models, out_dir / "contact-sheet.png")
        log(f"contact sheet: {sheet}")
    (out_dir / "results.json").write_text(json.dumps([asdict(r) for r in results], indent=2), encoding="utf-8")
    return results


def contact_sheet(results: list[ArtResult], models: list[str], out: Path, cell: int = 300) -> Path:
    cols = len(SHOOTOUT)
    rows = [m for m in models if any(r.model == m for r in results)]
    label_w, head_h = 170, 24
    sheet = Image.new("RGB", (label_w + cols * cell, head_h + len(rows) * cell), (236, 226, 204))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for c, (preset, _) in enumerate(SHOOTOUT):
        draw.text((label_w + c * cell + 6, 6), f"{c + 1}. {preset}", fill=(60, 40, 20), font=font)
    for r_i, model in enumerate(rows):
        y = head_h + r_i * cell
        mean = [r.seconds for r in results if r.model == model][1:] or [0]
        draw.text((6, y + 6), model, fill=(60, 40, 20), font=font)
        draw.text((6, y + 22), f"~{sum(mean) / len(mean):.0f}s/image", fill=(110, 80, 50), font=font)
        for res in (r for r in results if r.model == model):
            c = int(Path(res.path).name[:2]) - 1
            im = Image.open(res.path)
            im.thumbnail((cell - 8, cell - 8))
            sheet.paste(im, (label_w + c * cell + 4, y + 4))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out
