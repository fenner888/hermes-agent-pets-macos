#!/usr/bin/env python3
"""Validate a Hermes Agent Pets character package."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


SCHEMA = "hermes.agent_pet.character.v1"
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SAFE_STATE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SAFE_FRAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\.png$")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return data


def _is_png(path: Path) -> bool:
    try:
        return path.read_bytes()[: len(PNG_SIGNATURE)] == PNG_SIGNATURE
    except OSError:
        return False


def _is_webp(path: Path) -> bool:
    try:
        header = path.read_bytes()[:12]
    except OSError:
        return False
    return header[:4] == b"RIFF" and header[8:12] == b"WEBP"


def _sips_dimensions(path: Path) -> tuple[int, int] | None:
    if not shutil.which("sips"):
        return None
    try:
        result = subprocess.run(
            ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    width = height = None
    for line in result.stdout.splitlines():
        text = line.strip()
        if text.startswith("pixelWidth:"):
            width = int(text.split(":", 1)[1].strip())
        elif text.startswith("pixelHeight:"):
            height = int(text.split(":", 1)[1].strip())
    if width is None or height is None:
        return None
    return width, height


def validate_character(root: Path) -> tuple[list[str], list[str], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    manifest_path = root / "character.json"
    if not root.is_dir():
        return [f"character package is not a directory: {root}"], warnings, {}
    if not manifest_path.is_file():
        return [f"missing character.json: {manifest_path}"], warnings, {}

    try:
        manifest = _read_json(manifest_path)
    except Exception as exc:
        return [f"could not read character.json: {exc}"], warnings, {}

    if manifest.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")

    character_id = str(manifest.get("id") or "")
    if not SAFE_ID_RE.fullmatch(character_id):
        errors.append("id must use lowercase letters, numbers, '-' or '_' and start with a letter or number")
    if not str(manifest.get("displayName") or "").strip():
        errors.append("displayName is required")

    states = manifest.get("states")
    if not isinstance(states, dict) or not states:
        errors.append("states must be a non-empty object")
        states = {}
    if "idle" not in states:
        errors.append("states.idle is required")

    atlas = manifest.get("atlas")
    atlas_spritesheet_available = False
    if isinstance(atlas, dict):
        spritesheet = atlas.get("spritesheetPath")
        if spritesheet and (root / str(spritesheet)).is_file():
            atlas_spritesheet_available = True

    sprites_root = root / "sprites"
    has_frame_sources = sprites_root.is_dir()
    if not has_frame_sources and not atlas_spritesheet_available:
        errors.append(f"missing sprites directory or atlas spritesheet: {sprites_root}")
    elif not has_frame_sources:
        warnings.append("frame source folders were not checked because this is an atlas-only package")

    for state_name, raw_cfg in states.items():
        if not SAFE_STATE_RE.fullmatch(str(state_name)):
            errors.append(f"unsafe state name: {state_name}")
            continue
        if not isinstance(raw_cfg, dict):
            errors.append(f"state {state_name} must be an object")
            continue

        try:
            fps = float(raw_cfg.get("fps", 1))
        except (TypeError, ValueError):
            fps = 0
        if fps <= 0:
            errors.append(f"state {state_name} fps must be greater than zero")
        if "loop" in raw_cfg and not isinstance(raw_cfg.get("loop"), bool):
            errors.append(f"state {state_name} loop must be true or false")

        fallback = raw_cfg.get("fallback")
        if fallback and str(fallback) not in states:
            errors.append(f"state {state_name} fallback points at missing state: {fallback}")

        frames = raw_cfg.get("frames")
        if not isinstance(frames, list) or not frames:
            errors.append(f"state {state_name} frames must be a non-empty list")
            continue

        state_dir = sprites_root / str(state_name)
        if has_frame_sources and not state_dir.is_dir():
            errors.append(f"missing sprite state directory: sprites/{state_name}")
            continue

        for frame_name in frames:
            frame_text = str(frame_name)
            if not SAFE_FRAME_RE.fullmatch(frame_text) or "/" in frame_text or "\\" in frame_text:
                errors.append(f"unsafe frame filename in {state_name}: {frame_text}")
                continue
            if not has_frame_sources:
                continue
            frame_path = state_dir / frame_text
            if not frame_path.is_file():
                errors.append(f"missing frame: sprites/{state_name}/{frame_text}")
            elif not _is_png(frame_path):
                errors.append(f"frame is not a PNG: sprites/{state_name}/{frame_text}")

    if atlas is not None:
        if not isinstance(atlas, dict):
            errors.append("atlas must be an object")
        else:
            spritesheet = atlas.get("spritesheetPath")
            if spritesheet:
                spritesheet_path = root / str(spritesheet)
                if not spritesheet_path.is_file():
                    errors.append(f"missing atlas spritesheet: {spritesheet}")
                elif not _is_webp(spritesheet_path) and not _is_png(spritesheet_path):
                    errors.append(f"atlas spritesheet must be WEBP or PNG: {spritesheet}")

                dims = _sips_dimensions(spritesheet_path) if spritesheet_path.is_file() else None
                try:
                    expected_w = int(atlas.get("columns")) * int(atlas.get("cellWidth"))
                    expected_h = int(atlas.get("rows")) * int(atlas.get("cellHeight"))
                except (TypeError, ValueError):
                    expected_w = expected_h = 0
                if dims and expected_w and expected_h and dims != (expected_w, expected_h):
                    errors.append(f"atlas dimensions are {dims[0]}x{dims[1]}, expected {expected_w}x{expected_h}")
                elif not dims:
                    warnings.append("atlas dimensions were not checked because sips could not read them")

    pet_json = root / "pet.json"
    if pet_json.exists():
        try:
            _read_json(pet_json)
        except Exception as exc:
            errors.append(f"pet.json is invalid JSON: {exc}")

    return errors, warnings, manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Path to a character package directory.")
    parser.add_argument("--quiet", action="store_true", help="Only print errors.")
    args = parser.parse_args()

    root = Path(args.path).expanduser().resolve()
    errors, warnings, manifest = validate_character(root)
    if errors:
        print(f"Character validation failed: {root}")
        for error in errors:
            print(f"error: {error}")
        for warning in warnings:
            print(f"warning: {warning}")
        return 1

    if not args.quiet:
        states = manifest.get("states", {})
        print(f"Character validation passed: {manifest.get('id', root.name)}")
        print(f"Path: {root}")
        print(f"States: {', '.join(sorted(states))}")
        for warning in warnings:
            print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
