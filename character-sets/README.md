# Character Sets

Reusable character sources for Hermes Agent Pets.

Each public companion has its own directory:

```text
character-sets/
  koda/
  miko/
  bramble/
  nyx/
  pip/
  atlas/
```

Each character set should include:

- `character.json`: source manifest and animation metadata.
- `pet.json`: runtime metadata.
- `spritesheet.webp`: final 8x9 animated atlas.
- `assets/guard-peek-stop-no-panel.png`: stop-sign confirmation pose.
- `assets/stop-sign-run-front-strip.png`: front-facing stop-sign run-up strip.
- `assets/panel-shell.png`: confirmation panel shell.

Validate a character:

```bash
scripts/validate-hermes-pet.py character-sets/koda
```

Preview a character:

```bash
scripts/preview-hermes-pet.py character-sets/koda --output /tmp/koda-preview.html
```

Promote a character into the installable plugin:

```bash
scripts/package-hermes-pet.py --character character-sets/koda --plugin hermes-agent-pets/hermes-pet-agent --asset-id koda
```

Generated source frames stay local under ignored `sprites/` folders. The public repo tracks the final spritesheet and overlay assets needed at runtime.
