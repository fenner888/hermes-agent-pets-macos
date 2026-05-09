#!/usr/bin/env python3
"""Import saved companion concept images into the reference-art folder."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


COMPANION_IDS = ("koda", "miko", "bramble", "nyx", "pip", "atlas")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def import_image(source: Path, dest_dir: Path) -> Path:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"missing source image: {source}")
    suffix = source.suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise SystemExit(f"unsupported image type for {source}; expected one of {sorted(IMAGE_EXTENSIONS)}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"source{suffix}"
    if source != dest.resolve():
        shutil.copy2(source, dest)
    return dest


def update_companion_reference(roster_path: Path, companion_id: str, relative_path: str) -> None:
    roster = read_json(roster_path)
    companions = roster.get("companions")
    if not isinstance(companions, list):
        raise SystemExit(f"invalid roster companions list: {roster_path}")
    for companion in companions:
        if isinstance(companion, dict) and companion.get("id") == companion_id:
            reference = companion.setdefault("referenceArt", {})
            if not isinstance(reference, dict):
                reference = {}
                companion["referenceArt"] = reference
            reference["sourceStatus"] = "imported"
            reference["sourceImagePath"] = relative_path
            companion["artStatus"] = "concept-reference-imported"
            write_json(roster_path, roster)
            return
    raise SystemExit(f"companion not found in roster: {companion_id}")


def update_manifest(manifest_path: Path, companion_id: str, relative_path: str) -> None:
    manifest = read_json(manifest_path)
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise SystemExit(f"invalid reference-art manifest entries: {manifest_path}")
    for entry in entries:
        if isinstance(entry, dict) and entry.get("id") == companion_id:
            entry["sourceStatus"] = "imported"
            entry["sourceImagePath"] = relative_path
            imported_ids = {
                str(item.get("id"))
                for item in entries
                if isinstance(item, dict) and item.get("sourceStatus") == "imported"
            }
            manifest["sourceStatus"] = "fully-imported" if set(COMPANION_IDS) <= imported_ids else "partially-imported"
            write_json(manifest_path, manifest)
            return
    raise SystemExit(f"companion not found in reference-art manifest: {companion_id}")


def main() -> int:
    root = repo_root()
    parser = argparse.ArgumentParser(description=__doc__)
    for companion_id in COMPANION_IDS:
        parser.add_argument(f"--{companion_id}", type=Path, help=f"Source image for {companion_id}.")
    args = parser.parse_args()

    roster_path = root / "hermes-agent-pets" / "companions.json"
    manifest_path = root / "hermes-agent-pets" / "reference-art" / "manifest.json"
    imported = []
    for companion_id in COMPANION_IDS:
        source = getattr(args, companion_id)
        if source is None:
            continue
        dest = import_image(source, root / "hermes-agent-pets" / "reference-art" / companion_id)
        relative_path = str(dest.relative_to(root / "hermes-agent-pets"))
        update_companion_reference(roster_path, companion_id, relative_path)
        update_manifest(manifest_path, companion_id, relative_path)
        imported.append(f"{companion_id}: {dest}")

    if not imported:
        parser.error("provide at least one companion image argument")
    print("Imported companion reference art:")
    for line in imported:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
