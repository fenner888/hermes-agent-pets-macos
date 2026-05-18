# Hermes Pets Progress

Last updated: May 18, 2026.

## Current State

- The repo is now shaped as a public macOS Hermes Agent Pets project.
- The installable Hermes plugin lives at `hermes-agent-pets/hermes-pet-agent`.
- The native macOS overlay source lives at `scripts/hermes-pet-overlay/HermesPetOverlay.m`.
- The public starter companions are Koda, Miko, Bramble, Nyx, Pip, and Atlas.
- Personal/private character assets have been removed from public package paths.
- The default public companion is Koda.
- Current plugin version is `1.0.1`.
- `/pet help`, `/pet version`, `/pet status`, and `/pet update` report the installed plugin version.
- Audio-reactive dancing is not part of the bundled starter assets yet; `/pet dance on` reports unavailable for the current public companions.
- The plugin manifest and runtime now both cover Hermes LLM and tool lifecycle hooks.

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
- Tightened the dance guard so dance cannot be forced on unless the active pet actually ships dance assets.
- Tightened tool failure detection so benign successful output mentioning `"error"` or `timeout` does not trigger the failed/stop-sign escalation path.
- Expanded native overlay smoke coverage so all six bundled pets are launched with their spritesheet, stop pose, run-up strip, and panel shell.
- Expanded release doctor hygiene checks to catch `.DS_Store`, `__pycache__`, and `.pyc` files across public repo folders.

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

Latest pass, May 18, 2026:

- All six `scripts/validate-hermes-pet.py character-sets/<pet-id>` checks passed.
- `scripts/validate-hermes-companions.py` passed.
- `python3 -m py_compile hermes-agent-pets/hermes-pet-agent/__init__.py scripts/*.py` passed.
- `scripts/test-hermes-agent-pet.py` passed after adding manifest-hook and dance-env regression coverage.
- `scripts/test-hermes-agent-pet.py` now covers the false stop-sign regression: repeated successful output mentioning `"error"` or `timeout` keeps the pet in `succeeded` with `failure_count` at 0, while explicit tracebacks still count as failures.
- `scripts/smoke-install.sh` passed with a temp plugin install.
- A worktree tarball rehearsal through `install.sh` passed and the installed temp plugin passed `scripts/test-hermes-agent-pet.py --plugin`.
- A manual native overlay smoke loop launched Koda, Miko, Bramble, Nyx, Pip, and Atlas and verified idle, running, stop-sign, and confirm-delete states did not crash.
- `scripts/hermes-pet-doctor --build` passed with result `ready` after generated local cache cleanup.
- Stop-sign run-up strips were checked for all six public companions and are front-facing with the stop sign in hand.
- Runtime install rehearsal confirmed no `reference-art`, `.DS_Store`, `__pycache__`, or `.pyc` files are copied into the installed plugin.
- Reference-art PNG metadata was stripped to avoid false secret/token scan hits without changing the public artwork.
- Private character text audit outside ignored/generated folders returned no matches.
- Private character filename audit outside ignored/generated folders returned no matches.

## Known Blockers

- None currently known after the private character removal pass.

## Remaining / Upgrade Candidates

- Optional future work: add a visual pet picker instead of command-only pet selection.
- Optional future work: add real per-pet role systems for goals, skills, memory, reminders, and automation.
- Optional future work: add bundled dance strips if audio-reactive dancing becomes part of a release.
