# Custom Pets

Users should be able to create their own Hermes Agent Pets without using any private character from this repo.

The current public repo supports custom pet creation through reusable character sets and installable plugin assets. A custom pet is not yet a one-command import flow for end users, but the data format is intentionally simple and stable enough to build on.

## Character Set Shape

```text
character-sets/<pet-id>/
  character.json
  pet.json
  spritesheet.webp
  assets/
    guard-peek-stop-no-panel.png
    stop-sign-run-front-strip.png
    panel-shell.png
```

Required runtime files:

- `pet.json`: display metadata for the pet.
- `spritesheet.webp`: 8x9 animation atlas.
- `assets/guard-peek-stop-no-panel.png`: confirmation pose with the stop sign but without the panel.
- `assets/stop-sign-run-front-strip.png`: front-facing run-up strip used by the stop-sign animation.
- `assets/panel-shell.png`: confirmation panel shell.

Generated frame folders such as `sprites/idle/*.png` are source material and should stay ignored unless the project intentionally changes that policy.

## Validate A Custom Pet

```bash
scripts/validate-hermes-pet.py character-sets/koda
```

For your own pet:

```bash
scripts/validate-hermes-pet.py character-sets/<pet-id>
```

## Preview A Custom Pet

```bash
scripts/preview-hermes-pet.py character-sets/<pet-id> --output /tmp/<pet-id>-preview.html
```

Open the generated HTML locally to inspect the animation atlas and metadata.

## Promote A Custom Pet Into The Plugin

```bash
scripts/package-hermes-pet.py \
  --character character-sets/<pet-id> \
  --plugin hermes-agent-pets/hermes-pet-agent \
  --asset-id <pet-id>
```

Then install or rehearse:

```bash
HERMES_PLUGIN_DIR=/tmp/hermes-plugin-test scripts/install-hermes-agent-pet.sh
scripts/test-hermes-agent-pet.py --plugin /tmp/hermes-plugin-test/hermes-pet-agent
```

## Design Guidance

Hermes Agent Pets should feel like native desktop companion agents, not generic mascots.

Good fit:

- Humanoid robot companions.
- Animal-inspired silhouette, ears, visor, tail, posture, or motion.
- Clear readable expression at small sizes.
- States that communicate Hermes work: thinking, working, success, blocked, error, reminding, learning, recalling.

Avoid:

- Private/personal characters.
- Normal unmodified animals.
- Plush-toy mascots.
- Random fantasy creatures unrelated to Hermes.
- Assets copied from another project without clear permission.

## Future Import Flow

A future public release should add a user-facing import command such as:

```bash
scripts/import-custom-pet.sh /path/to/pet-package
```

Until then, custom pet creation is a contributor/developer workflow using the validator, previewer, and package script above.
