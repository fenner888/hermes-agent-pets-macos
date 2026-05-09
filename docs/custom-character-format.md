# Custom Character Format

This repo uses `character.json` to describe reusable Hermes pet character art.

The format is intentionally small. It supports both the current Codex-style atlas and a future frame-folder renderer.

## Required Shape

```text
character-sets/<character-id>/
  character.json
  pet.json
  spritesheet.webp
```

Optional release files:

```text
assets/
  guard-peek-stop-no-panel.png
  stop-sign-run-front-strip.png
  panel-shell.png
sprites/
  idle/
    idle_00.png
README.md
```

For release builds, `spritesheet.webp` is enough when `character.json` includes
an `atlas` block. Per-frame `sprites/` folders are useful source material for
preview/debug tooling, but they are generated and do not need to be committed.

## Metadata

```json
{
  "schema": "hermes.agent_pet.character.v1",
  "id": "koda",
  "displayName": "Koda",
  "description": "A humanoid robot wolf companion.",
  "states": {
    "idle": {
      "fps": 4,
      "loop": true,
      "frames": ["idle_00.png"]
    }
  }
}
```

## State Rules

- `idle` is required.
- State names must use letters, numbers, `_`, or `-`.
- Frame names must be simple `.png` filenames with no path separators.
- Optional states may include `fallback`; the fallback must name another state.
- Missing optional states should fall back to `idle`.

Recommended states:

```text
idle
running-right
running-left
waving
jumping
failed
waiting
running
review
```

Future-friendly aliases:

```text
message
bubble
approval-needed
success
```

## Atlas Support

Character sets may also include:

```json
{
  "atlas": {
    "spritesheetPath": "spritesheet.webp",
    "columns": 8,
    "rows": 9,
    "cellWidth": 192,
    "cellHeight": 208
  }
}
```

The atlas lets the same character promote into Codex-style pet packages and the current macOS Hermes pet overlay.
