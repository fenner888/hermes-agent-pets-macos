#!/usr/bin/env python3
"""Promote a validated character set into a Hermes agent pet plugin."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


EXTRA_ASSET_NAMES = (
    "guard-peek-stop.png",
    "guard-peek-stop-no-panel.png",
    "stop-sign-run-front-strip.png",
    "stop-sign.png",
    "panel-shell.png",
    "dance-bob-strip.png",
    "dance-step-strip.png",
    "dance-hit-strip.png",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return data


def _run_validator(repo: Path, character_dir: Path) -> None:
    validator = repo / "scripts" / "validate-hermes-pet.py"
    result = subprocess.run(
        [sys.executable, str(validator), str(character_dir), "--quiet"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        output = (result.stdout + result.stderr).strip()
        raise SystemExit(output or f"character validation failed: {character_dir}")


def _copy_file(source: Path, dest: Path, copied: list[str]) -> None:
    if not source.is_file():
        raise SystemExit(f"missing required source file: {source}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    copied.append(str(dest))


def _copy_optional(source: Path, dest: Path, copied: list[str]) -> bool:
    if not source.is_file():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == dest.resolve():
        return True
    shutil.copy2(source, dest)
    copied.append(str(dest))
    return True


def promote_character(character_dir: Path, plugin_dir: Path, asset_id: str | None = None) -> list[str]:
    repo = _repo_root()
    character_dir = character_dir.expanduser().resolve()
    plugin_dir = plugin_dir.expanduser().resolve()
    _run_validator(repo, character_dir)

    manifest = _read_json(character_dir / "character.json")
    pet_id = asset_id or str(manifest.get("id") or character_dir.name)
    dest_assets = plugin_dir / "assets" / pet_id
    copied: list[str] = []

    atlas = manifest.get("atlas") if isinstance(manifest.get("atlas"), dict) else {}
    spritesheet_name = str(atlas.get("spritesheetPath") or "spritesheet.webp")
    _copy_file(character_dir / "pet.json", dest_assets / "pet.json", copied)
    _copy_file(character_dir / spritesheet_name, dest_assets / "spritesheet.webp", copied)

    for name in EXTRA_ASSET_NAMES:
        sources = (
            character_dir / "assets" / name,
            repo / "assets" / pet_id / name,
            dest_assets / name,
        )
        if any(_copy_optional(source, dest_assets / name, copied) for source in sources):
            continue
    return copied


def main() -> int:
    repo = _repo_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character", default=repo / "character-sets" / "koda", help="Character set directory.")
    parser.add_argument("--plugin", default=repo / "hermes-agent-pets" / "hermes-pet-agent", help="Hermes plugin directory.")
    parser.add_argument("--asset-id", default=None, help="Destination asset folder name. Defaults to character id.")
    args = parser.parse_args()

    copied = promote_character(Path(args.character), Path(args.plugin), args.asset_id)
    print(f"Promoted character into {Path(args.plugin).expanduser().resolve()}")
    for path in copied:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
