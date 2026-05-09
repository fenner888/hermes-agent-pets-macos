# Release Checklist

Use this before publishing the public macOS Hermes Agent Pets repo.

## Assets

```bash
scripts/validate-hermes-pet.py character-sets/koda
scripts/validate-hermes-pet.py character-sets/miko
scripts/validate-hermes-pet.py character-sets/bramble
scripts/validate-hermes-pet.py character-sets/nyx
scripts/validate-hermes-pet.py character-sets/pip
scripts/validate-hermes-pet.py character-sets/atlas
scripts/validate-hermes-companions.py
```

Confirm each public starter pet has:

- `pet.json`
- `spritesheet.webp`
- `assets/guard-peek-stop-no-panel.png`
- `assets/stop-sign-run-front-strip.png`
- `assets/panel-shell.png`

## Package

```bash
scripts/install-hermes-agent-pet.sh
```

Expected package:

```text
hermes-agent-pets/hermes-pet-agent/plugin.yaml
hermes-agent-pets/hermes-pet-agent/__init__.py
hermes-agent-pets/hermes-pet-agent/assets/koda/spritesheet.webp
```

## Overlay

```bash
scripts/hermes-pet-overlay/build.sh
```

Expected binary:

```text
build/HermesPetOverlay.app/Contents/MacOS/hermes-pet-overlay
```

## Clean Install Rehearsal

```bash
HERMES_PLUGIN_DIR=/tmp/hermes-plugin-test scripts/install-hermes-agent-pet.sh
scripts/test-hermes-agent-pet.py --plugin /tmp/hermes-plugin-test/hermes-pet-agent
scripts/smoke-install.sh
```

Expected temp package:

```text
/tmp/hermes-plugin-test/hermes-pet-agent/plugin.yaml
/tmp/hermes-plugin-test/hermes-pet-agent/__init__.py
/tmp/hermes-plugin-test/hermes-pet-agent/bin/hermes-pet-overlay
/tmp/hermes-plugin-test/hermes-pet-agent/assets/koda/spritesheet.webp
```

## Public Repo Check

```bash
scripts/hermes-pet-doctor --build
rg -n -i "private character|local-only" .
```

Before release, confirm:

- No personal/private character assets are tracked.
- No local machine paths are embedded.
- No generated frame PNG folders are staged.
- No `.DS_Store`, `__pycache__`, `.pyc`, or generated local cache files are present in release folders.
- Binary/artifact scans do not expose private names, local paths, or real secrets.
- `LICENSE` uses MIT with `Copyright (c) 2026 Mark Fenner`.
- README license language covers bundled starter companion assets.
- Tracked release assets are intentionally included; use Git LFS or release downloads before adding much larger future asset sets.
- `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CUSTOM_PETS.md`, issue templates, and PR template are present.
- `scripts/smoke-install.sh` passes; run `scripts/smoke-install.sh --overlay` when GUI access is available.
