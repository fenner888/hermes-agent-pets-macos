# Hermes Agent Pets

This folder is the source of truth for Hermes-native pet packages.

```text
hermes-agent-pets/
  hermes-pet-agent/
    plugin.yaml
    __init__.py
    assets/
      koda/
      miko/
      bramble/
      nyx/
      pip/
      atlas/
  companions.json
  placeholders/
  reference-art/
```

Keep this folder clean:

- Include only installable plugin code, pet metadata, and release assets.
- Do not commit `__pycache__/`, local backups, build output, virtualenvs, or hatch run work files.
- Keep generated hatch QA in `hatch-runs/` and promote only final release assets into the pet package.
- The native overlay should resolve from `HERMES_PET_OVERLAY_EXE`, bundled `bin/hermes-pet-overlay`, or this repo's `build/HermesPetOverlay.app` during development.

Shared companion data:

- `companions.json`: centralized Hermes companion roster and state model.
- `placeholders/`: traceable placeholder SVGs for future companions.
- `reference-art/`: manifest and imported source concept images.
- Validate with `scripts/validate-hermes-companions.py`.

Current public starter companions:

- Koda: goal guardian.
- Miko: skill scout.
- Bramble: deep work anchor.
- Nyx: stealth automation companion.
- Pip: reminder/check-in companion.
- Atlas: memory and insight companion.

Personal/private characters are intentionally excluded from this public package.
