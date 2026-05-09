#!/usr/bin/env python3
"""Create a standalone HTML preview for a Hermes character package."""

from __future__ import annotations

import argparse
import base64
import html
import json
from pathlib import Path
from typing import Any


STATE_ORDER = (
    "idle",
    "running-right",
    "running-left",
    "running",
    "waiting",
    "review",
    "waving",
    "jumping",
    "failed",
)


def _read_manifest(root: Path) -> dict[str, Any]:
    data = json.loads((root / "character.json").read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("character.json must contain a JSON object")
    return data


def _ordered_states(states: dict[str, Any]) -> list[str]:
    ordered = [state for state in STATE_ORDER if state in states]
    ordered.extend(sorted(state for state in states if state not in ordered))
    return ordered


def _data_uri(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def _state_frame_items(root: Path, state: str, config: dict[str, Any]) -> list[dict[str, str]]:
    items = []
    for frame in config.get("frames", []):
        frame_name = str(frame)
        path = root / "sprites" / state / frame_name
        if not path.is_file():
            continue
        items.append({"name": frame_name, "src": _data_uri(path)})
    return items


def render_preview(root: Path, manifest: dict[str, Any]) -> str:
    states = manifest.get("states") if isinstance(manifest.get("states"), dict) else {}
    frame_data: dict[str, list[dict[str, str]]] = {}
    state_meta: dict[str, dict[str, Any]] = {}
    cards = []

    for state in _ordered_states(states):
        raw_config = states[state] if isinstance(states[state], dict) else {}
        frames = _state_frame_items(root, state, raw_config)
        frame_data[state] = frames
        state_meta[state] = {
            "fps": raw_config.get("fps", 1),
            "loop": raw_config.get("loop", True),
            "fallback": raw_config.get("fallback", ""),
            "frameCount": len(frames),
        }
        first_src = frames[0]["src"] if frames else ""
        fallback = raw_config.get("fallback") or "none"
        loop = "loop" if raw_config.get("loop", True) else "one-shot"
        cards.append(
            f"""
      <section class="state-card" data-state="{html.escape(state)}">
        <div class="sprite-stage">
          <img alt="{html.escape(state)} preview" src="{first_src}" data-frame-index="0">
        </div>
        <h2>{html.escape(state)}</h2>
        <p>{len(frames)} frame(s), {html.escape(str(raw_config.get("fps", 1)))} fps, {loop}, fallback: {html.escape(str(fallback))}</p>
      </section>"""
        )

    title = html.escape(str(manifest.get("displayName") or manifest.get("id") or root.name))
    description = html.escape(str(manifest.get("description") or ""))
    frame_json = json.dumps(frame_data, separators=(",", ":"))
    meta_json = json.dumps(state_meta, separators=(",", ":"))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} Hermes pet preview</title>
  <style>
    :root {{
      color-scheme: dark;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #101416;
      color: #edf5f2;
    }}
    body {{
      margin: 0;
      padding: 28px;
    }}
    header {{
      max-width: 1080px;
      margin: 0 auto 24px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 30px;
      letter-spacing: 0;
    }}
    .meta {{
      margin: 0;
      color: #b8c9c3;
      line-height: 1.5;
      overflow-wrap: anywhere;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      max-width: 1080px;
      margin: 0 auto;
    }}
    .state-card {{
      border: 1px solid #334541;
      border-radius: 8px;
      background: #18211f;
      padding: 14px;
    }}
    .sprite-stage {{
      display: grid;
      place-items: center;
      height: 178px;
      border-radius: 6px;
      background:
        linear-gradient(45deg, #22302c 25%, transparent 25%),
        linear-gradient(-45deg, #22302c 25%, transparent 25%),
        linear-gradient(45deg, transparent 75%, #22302c 75%),
        linear-gradient(-45deg, transparent 75%, #22302c 75%);
      background-size: 24px 24px;
      background-position: 0 0, 0 12px, 12px -12px, -12px 0;
    }}
    img {{
      max-width: 150px;
      max-height: 162px;
      image-rendering: pixelated;
    }}
    h2 {{
      margin: 12px 0 4px;
      font-size: 16px;
      letter-spacing: 0;
    }}
    p {{
      margin: 0;
      color: #b8c9c3;
      font-size: 14px;
      line-height: 1.45;
    }}
  </style>
</head>
<body>
  <header>
    <h1>{title}</h1>
    <p class="meta">{description}<br>Package: {html.escape(str(root))}</p>
  </header>
  <main class="grid">
    {''.join(cards)}
  </main>
  <script>
    const framesByState = {frame_json};
    const stateMeta = {meta_json};
    for (const card of document.querySelectorAll('.state-card')) {{
      const state = card.dataset.state;
      const img = card.querySelector('img');
      const frames = framesByState[state] || [];
      const meta = stateMeta[state] || {{}};
      if (!img || frames.length < 2) continue;
      let index = 0;
      const interval = Math.max(80, Math.round(1000 / Math.max(1, Number(meta.fps || 1))));
      window.setInterval(() => {{
        if (meta.loop === false && index >= frames.length - 1) return;
        index = (index + 1) % frames.length;
        img.src = frames[index].src;
        img.dataset.frameIndex = String(index);
      }}, interval);
    }}
  </script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Path to a character package directory.")
    parser.add_argument("--output", help="Output HTML path. Defaults to <package>/<id>-preview.html.")
    args = parser.parse_args()

    root = Path(args.path).expanduser().resolve()
    manifest = _read_manifest(root)
    package_id = str(manifest.get("id") or root.name)
    output = Path(args.output).expanduser().resolve() if args.output else root / f"{package_id}-preview.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_preview(root, manifest), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
