# Image models (Lemonade)

Ringwraith generates its art through a local [Lemonade](https://lemonade-server.ai) server, which
uses its stable-diffusion.cpp backend. The model choice was tested on an RTX 3080 Ti (12 GB) in
November 2026.

| Model | Role | Speed (768×1024) | Notes |
|---|---|---|---|
| `Z-Image-Turbo-Q8B` (custom) | **default** | ~11 s | Z-Image's painterly look. Its diffusion model is quantized so it fits in VRAM. |
| `Flux-2-Klein-4B` (built-in) | references and fallback | ~5 s (edit) | Paints scenes from character portraits; also the last retry for failed jobs |
| `RealESRGAN-x4plus` (built-in) | upscaler | ~8 s | Sharpens reference edits up to full size |

The first image after a model loads takes about 100 s extra. Switching models costs a reload, so
stick to one model per session.

## Consistent faces: painting from portraits
When a picture names characters (`set_scene` / `queue_art` with `characters`, or `art queue --with`), their
portraits are used as references:
1. **Flux-2-Klein-4B** paints through Lemonade's `/images/edits` with up to 3 portraits as reference images.
   The prompt names them: "image 1 shows Tomas Briarcleave…".
2. Edits must stay under about 400k pixels on a 12 GB card; larger ones fail with
   "generate_image returned no results". So a wide scene is painted at 960×384, a portrait at 512×704.
   References are shrunk to 512 px.
3. **RealESRGAN-x4plus** upscales the edit (`/images/upscale`, about 8 s). The result is blended 40/60 with
   a plain Lanczos resize, because RealESRGAN alone smooths away the brushwork.
4. Then the usual night or dusk grade.

Pictures without named characters use Z-Image as before. Switching between the two models costs a
reload (about 100 s). The art worker prefers jobs for the model that is already loaded, and frees the GPU
for whichever model its first job needs.

## Creating the custom Z-Image model

The built-in `Z-Image-Turbo` ships a 12 GB bf16 diffusion model. That model and its 8 GB text
encoder don't both fit in 12 GB of VRAM, so sd-server offloads them and takes about 65 s per image.
The custom model swaps in leejet's Q8_0 GGUF diffusion model and keeps the original safetensors
text encoder and VAE:

```sh
lemonade pull user.Z-Image-Turbo-Q8B \
  --checkpoint main leejet/Z-Image-Turbo-GGUF:z_image_turbo-Q8_0.gguf \
  --checkpoint text_encoder Comfy-Org/z_image_turbo:split_files/text_encoders/qwen_3_4b.safetensors \
  --checkpoint vae Comfy-Org/z_image_turbo:split_files/vae/ae.safetensors \
  --recipe sd-cpp
```

Steps 9 and cfg 1.0 are passed per request (`MODEL_PARAMS` in `tools/ringwraith/art.py`), because
custom models carry no Lemonade defaults.

**Don't use a GGUF text encoder.** With `unsloth/Qwen3-4B-Instruct-2507-GGUF` (Q8_0), sd-server
produced exactly one image per load and then failed every request with
`generate_image returned no results`.

## Sketches
Besides paintings, Ringwraith draws small pencil sketches into the tale (`sketch`, 768×512) of what the hero
hears of but doesn't see: a place in a story told by the fire, a creature in a rumour, the tower in a letter.
The paintings on the stage stay for what is happening. A sketch uses its own pencil-on-parchment prompt, not
the house style, and needs no extra setup. Sketches go to `90 Assets/sketches/`.

## Your own style LoRA (optional)
A LoRA trained for the main model (Z-Image Turbo) can add **looks** to the house style: Ringwraith picks one for a
picture when the scene fits what you wrote about it. Set it up in the campaign's
`.ringwraith/settings.yaml`, under `art`:

```yaml
art:
  lora:
    file: D:/AI/loras/my-style.safetensors   # absolute path
    strength: 0.6                            # for every look that doesn't set its own
    looks:
      painted:                               # the look's name, as Ringwraith passes it
        words: "mystyle painting."           # put first in the prompt: usually your trigger words
        house_style: true                    # keep the house style's prompt after the words
        when: quiet, secret, sombre, tense, ruined or night scenes
      bright:
        words: "mystyle illustration."
        house_style: false                   # only the subject, mood and time after the words
        strength: 0.8
        when: warm, cheerful or heroic scenes by day
      sketch:                                # a look named "sketch" is used for every sketch
        words: "mystyle illustration."
```

- The looks are added to Ringwraith's instructions when the table starts, with your `when` lines, so restart
  `ringwraith serve` after changing them. Leave `art.lora` out (or `null`) to play without.
- A picture with a look is painted by the main model without portrait references, since the LoRA fits only that
  model. Ringwraith leaves the look out when a named character's face matters.
- The night, dusk and ruin colour grades belong to the house style; a look gets none, since a style LoRA brings
  its own light and the grade on top of it goes too dark.
- Lemonade needs no extra setup. Ringwraith sends the LoRA with each request in sd-server's
  `<sd_cpp_extra_args>` block (`art.lora_args`). sd-server reads only the first such block, so that block also
  carries the seed, steps, cfg and negative prompt that Lemonade would otherwise send. The `<lora:…>` prompt
  syntax isn't read on this route.
- A LoRA adds well under a second per picture. Try strengths around 0.6 first: at 1.0 a style LoRA often
  overpowers the prompt.
- If the file is missing or a look is unknown, the picture is painted in the house style and the art worker logs
  why.

## Troubleshooting
- **`generate_image returned no results`:** sd-server is stuck, or VRAM is full. Other GPU apps, such
  as games or a stale model Lemonade still holds, cause this. The art worker unloads other sd-cpp
  models when it starts, and `art.generate` unloads and retries once. Check with `nvidia-smi`, and
  run `lemonade unload` to clear everything.
- **Comparing models:** `ringwraith art test <model...>` writes a comparison sheet to `build/art-test/`.
