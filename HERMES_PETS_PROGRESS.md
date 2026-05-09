# Hermes Pets Progress

Last updated: May 8, 2026.

## Current State

- The repo is now shaped as a public macOS Hermes Agent Pets project.
- The installable Hermes plugin lives at `hermes-agent-pets/hermes-pet-agent`.
- The native macOS overlay source lives at `scripts/hermes-pet-overlay/HermesPetOverlay.m`.
- The public starter companions are Koda, Miko, Bramble, Nyx, Pip, and Atlas.
- Personal/private character assets have been removed from public package paths.
- The default public companion is Koda.
- Audio-reactive dancing is off by default and opt-in through `/pet dance on`.

## Relevant Files

- `hermes-agent-pets/hermes-pet-agent/__init__.py`: Hermes plugin, `/pet` command, state handling, overlay launch, deletion confirmation flow.
- `hermes-agent-pets/hermes-pet-agent/plugin.yaml`: Hermes plugin manifest.
- `hermes-agent-pets/companions.json`: centralized companion roster and Hermes state model.
- `character-sets/<pet-id>/pet.json`: runtime pet metadata.
- `character-sets/<pet-id>/spritesheet.webp`: final runtime animation atlas.
- `character-sets/<pet-id>/assets/guard-peek-stop-no-panel.png`: stop-sign confirmation pose.
- `character-sets/<pet-id>/assets/stop-sign-run-front-strip.png`: front-facing stop-sign run-up strip.
- `character-sets/<pet-id>/assets/panel-shell.png`: confirmation panel shell.
- `scripts/hermes-pet-overlay/build.sh`: native overlay build.
- `scripts/install-hermes-agent-pet.sh`: plugin installer.
- `scripts/test-hermes-agent-pet.py`: runtime regression checks.
- `scripts/hermes-pet-doctor`: clean-release audit.

## Completed

- Added reusable character data for six public humanoid robot animal companions.
- Added Hermes state support for `idle`, `thinking`, `working`, `success`, `blocked`, `error`, `sleeping`, `reminding`, `learning`, and `recalling`.
- Added pet switching with `/pet companion <id>`.
- Added custom stop-sign pose, front-facing run-up strip, and panel shell support per companion.
- Added a clean installer that copies only runtime plugin assets, the companion roster, and the native overlay binary.
- Hardened the installer against path-like plugin names and local cache/metadata leakage.
- Added MIT license with `Copyright (c) 2026 Mark Fenner`.
- Renamed the public package and overlay from character-specific names to Hermes Pet names.
- Removed private/personal character assets from the public repo package.
- Added public repo readiness docs: `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CUSTOM_PETS.md`, GitHub issue templates, and a PR template.
- Added `scripts/smoke-install.sh` for repeatable temp install rehearsals.

## Validation Results

```bash
scripts/validate-hermes-pet.py character-sets/koda
scripts/validate-hermes-pet.py character-sets/miko
scripts/validate-hermes-pet.py character-sets/bramble
scripts/validate-hermes-pet.py character-sets/nyx
scripts/validate-hermes-pet.py character-sets/pip
scripts/validate-hermes-pet.py character-sets/atlas
scripts/validate-hermes-companions.py
scripts/hermes-pet-overlay/build.sh
scripts/test-hermes-agent-pet.py
HERMES_PLUGIN_DIR=/tmp/hermes-plugin-test scripts/install-hermes-agent-pet.sh
scripts/test-hermes-agent-pet.py --plugin /tmp/hermes-plugin-test/hermes-pet-agent
```

Latest pass:

- All six `scripts/validate-hermes-pet.py character-sets/<pet-id>` checks passed.
- `scripts/validate-hermes-companions.py` passed.
- `scripts/hermes-pet-overlay/build.sh` passed and produced `build/HermesPetOverlay.app`.
- `scripts/test-hermes-agent-pet.py` passed.
- `scripts/test-hermes-agent-pet.py --overlay` passed; the native macOS overlay launched and responded to state-file changes.
- `scripts/hermes-pet-doctor --build` passed with result `ready`.
- `HERMES_PLUGIN_DIR=/tmp/hermes-plugin-test scripts/install-hermes-agent-pet.sh` passed.
- `scripts/test-hermes-agent-pet.py --plugin /tmp/hermes-plugin-test/hermes-pet-agent` passed.
- `scripts/smoke-install.sh` passed.
- `scripts/smoke-install.sh --overlay` passed and launched the temp-installed plugin binary.
- Stop-sign run-up strips were visually checked for all six public companions and are front-facing with the stop sign in hand.
- Runtime install rehearsal confirmed no `reference-art`, `.DS_Store`, `__pycache__`, or `.pyc` files are copied into the installed plugin.
- Reference-art PNG metadata was stripped to avoid false secret/token scan hits without changing the public artwork.
- Private character text audit outside ignored/generated folders returned no matches.
- Private character filename audit outside ignored/generated folders returned no matches.

## Known Blockers

- None currently known after the private character removal pass.

## Remaining Before Public GitHub

- Final first-time-user README skim.
- Confirm the target GitHub remote/repo name, then push when ready.
