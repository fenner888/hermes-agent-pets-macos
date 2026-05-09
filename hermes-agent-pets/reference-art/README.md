# Companion Reference Art

This folder is for canonical concept/reference images used to generate future Hermes companion spritesheets.

The public starter companions have final visual direction from the provided reference images. The roster keeps validated metadata so each companion can be regenerated or improved without depending on private character art.

## Expected Source Files

Save or import the provided images into these locations:

```text
hermes-agent-pets/reference-art/koda/source.png
hermes-agent-pets/reference-art/miko/source.png
hermes-agent-pets/reference-art/bramble/source.png
hermes-agent-pets/reference-art/nyx/source.png
hermes-agent-pets/reference-art/pip/source.png
hermes-agent-pets/reference-art/atlas/source.png
```

Use the helper script when the files are available elsewhere:

```bash
scripts/import-companion-reference-art.py \
  --koda /path/to/koda.png \
  --miko /path/to/miko.png \
  --bramble /path/to/bramble.png \
  --nyx /path/to/nyx.png \
  --pip /path/to/pip.png \
  --atlas /path/to/atlas.png
```

## Image Mapping

1. `koda`: wolf/dog goal guardian, dark gunmetal armor, amber eyes/core, small blue accent LEDs.
2. `miko`: fox skill scout, agile dark armor, orange eyes/core, orange and cyan light strips.
3. `bramble`: bear deep-work anchor, heavy rounded dark armor, blue eyes/core, bronze claw details.
4. `nyx`: cat/panther stealth automation companion, dark smooth armor, violet eyes/core/accent LEDs.
5. `pip`: rabbit reminder/check-in companion, compact frame, green eyes/core, long mechanical ears.
6. `atlas`: owl/eagle memory companion, wing-like shoulders, blue eyes/core, gold beak/claw/trim.

## Sprite Generation Notes

- Final assets should become `character-sets/<id>/character.json`, `pet.json`, `spritesheet.webp`, and frame folders.
- Keep a readable desktop scale at small macOS overlay sizes.
- Reduce the high-detail concept art into clean, small-size animation silhouettes.
- Preserve each companion's role color: amber for Koda/Miko, blue for Bramble/Atlas, violet for Nyx, green for Pip.
