# Workflows ComfyUI

Exporter depuis ComfyUI en **format API** (`Save (API format)`) et nommer :

- `ltx_t2v.json` : LTX-Video text-to-video (576×1024, 24 fps)
- `wan_t2v.json` : Wan 2.1 1.3B text-to-video (480×832, 16 fps)

Le step `generate_clip` remplace les entrées des nœuds dont le titre (`_meta.title`) vaut :
`PROMPT` (texte positif), `NEGATIVE`, `SIZE` (width / height / length) et `SEED`.
Renommer les nœuds dans ComfyUI (clic droit → *Title*) avant d'exporter.
