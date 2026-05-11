# Hermes Pet Agent

Installable Hermes plugin for native macOS companion pets.

Bundled public starter assets live under:

```text
assets/koda/
assets/miko/
assets/bramble/
assets/nyx/
assets/pip/
assets/atlas/
```

Each packaged pet includes:

- `pet.json`
- `spritesheet.webp`
- `guard-peek-stop-no-panel.png`
- `stop-sign-run-front-strip.png`
- `panel-shell.png`

Overlay resolution order:

1. `HERMES_PET_OVERLAY_EXE`
2. `bin/hermes-pet-overlay` inside this plugin
3. `HermesPetOverlay.app/Contents/MacOS/hermes-pet-overlay` inside this plugin
4. This repo's `build/HermesPetOverlay.app/Contents/MacOS/hermes-pet-overlay`

Build and install from the repo root:

```bash
scripts/hermes-pet-overlay/build.sh
scripts/install-hermes-agent-pet.sh
```

After restarting Hermes:

```text
/pet help
/pet wake
/pet companions
/pet companion koda
/pet version
```

Audio-reactive dancing is not part of the bundled starter assets yet. The command exists for future pets that include dance strips, but the current starter set reports dance as unavailable:

```text
/pet dance on
```
