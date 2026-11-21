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

## Troubleshooting
- **`generate_image returned no results`:** sd-server is stuck, or VRAM is full. Other GPU apps, such
  as games or a stale model Lemonade still holds, cause this. The art worker unloads other sd-cpp
  models when it starts, and `art.generate` unloads and retries once. Check with `nvidia-smi`, and
  run `lemonade unload` to clear everything.
- **Comparing models:** `ringwraith art test <model...>` writes a comparison sheet to `build/art-test/`.
