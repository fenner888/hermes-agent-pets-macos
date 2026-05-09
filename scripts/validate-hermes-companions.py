#!/usr/bin/env python3
"""Validate the centralized Hermes companion roster."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SCHEMA = "hermes.agent_pet.roster.v1"
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
REQUIRED_COMPANION_FIELDS = (
    "id",
    "name",
    "animalInspiration",
    "hermesRole",
    "personality",
    "shortBio",
    "visualDescription",
    "primaryColor",
    "secondaryColor",
    "accentColor",
    "defaultState",
    "supportedStates",
    "imagePlaceholderPath",
    "spritePlaceholderPath",
    "suggestedAnimationNotes",
    "useCaseInsideHermes",
)
REQUIRED_STATES = (
    "idle",
    "thinking",
    "working",
    "success",
    "blocked",
    "error",
    "sleeping",
    "reminding",
    "learning",
    "recalling",
)
PLACEHOLDER_ART_STATUSES = {
    "metadata-placeholder",
    "concept-reference-pending-import",
}


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return data


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _is_safe_relative_path(relative_path: str) -> bool:
    if not relative_path or relative_path.startswith("/") or ".." in Path(relative_path).parts:
        return False
    return True


def _asset_exists(roster_dir: Path, relative_path: str) -> bool:
    if not _is_safe_relative_path(relative_path):
        return False
    return (roster_dir / relative_path).is_file()


def validate_roster(path: Path) -> tuple[list[str], list[str], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        roster = _read_json(path)
    except Exception as exc:
        return [f"could not read roster: {exc}"], warnings, {}

    roster_dir = path.parent
    if roster.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")

    state_model = roster.get("stateModel")
    if not isinstance(state_model, dict):
        errors.append("stateModel must be an object")
        state_model = {}

    required_states = state_model.get("requiredStates")
    if required_states != list(REQUIRED_STATES):
        errors.append("stateModel.requiredStates must match the Hermes state contract")

    states = state_model.get("states")
    if not isinstance(states, list) or not states:
        errors.append("stateModel.states must be a non-empty list")
        states = []

    state_ids: set[str] = set()
    for index, raw_state in enumerate(states):
        if not isinstance(raw_state, dict):
            errors.append(f"stateModel.states[{index}] must be an object")
            continue
        state_id = str(raw_state.get("id") or "")
        if state_id not in REQUIRED_STATES:
            errors.append(f"unsupported state id in stateModel: {state_id}")
        if state_id in state_ids:
            errors.append(f"duplicate state id in stateModel: {state_id}")
        state_ids.add(state_id)
        for field in ("label", "description", "overlayFallback"):
            if not str(raw_state.get(field) or "").strip():
                errors.append(f"state {state_id or index} missing {field}")
    missing_states = [state for state in REQUIRED_STATES if state not in state_ids]
    if missing_states:
        errors.append("missing state definitions: " + ", ".join(missing_states))

    companions = roster.get("companions")
    if not isinstance(companions, list) or not companions:
        errors.append("companions must be a non-empty list")
        companions = []

    companion_ids: set[str] = set()
    for index, raw_companion in enumerate(companions):
        if not isinstance(raw_companion, dict):
            errors.append(f"companions[{index}] must be an object")
            continue
        companion_id = str(raw_companion.get("id") or "")
        if not SAFE_ID_RE.fullmatch(companion_id):
            errors.append(f"unsafe companion id: {companion_id or index}")
        if companion_id in companion_ids:
            errors.append(f"duplicate companion id: {companion_id}")
        companion_ids.add(companion_id)

        for field in REQUIRED_COMPANION_FIELDS:
            value = raw_companion.get(field)
            if isinstance(value, str):
                if not value.strip():
                    errors.append(f"companion {companion_id or index} missing {field}")
            elif isinstance(value, list):
                if not value:
                    errors.append(f"companion {companion_id or index} missing {field}")
            elif value is None:
                errors.append(f"companion {companion_id or index} missing {field}")

        for field in ("primaryColor", "secondaryColor", "accentColor"):
            if not HEX_COLOR_RE.fullmatch(str(raw_companion.get(field) or "")):
                errors.append(f"companion {companion_id or index} has invalid {field}")

        supported_states = raw_companion.get("supportedStates")
        if not isinstance(supported_states, list):
            errors.append(f"companion {companion_id or index} supportedStates must be a list")
            supported_states = []
        unsupported = [state for state in supported_states if state not in state_ids]
        if unsupported:
            errors.append(f"companion {companion_id or index} references unknown states: {', '.join(unsupported)}")
        for state in REQUIRED_STATES:
            if state not in supported_states:
                errors.append(f"companion {companion_id or index} missing supported state: {state}")
        if raw_companion.get("defaultState") not in supported_states:
            errors.append(f"companion {companion_id or index} defaultState is not supported")

        for field in ("imagePlaceholderPath", "spritePlaceholderPath"):
            relative_path = str(raw_companion.get(field) or "")
            if not _asset_exists(roster_dir, relative_path):
                errors.append(f"companion {companion_id or index} missing {field}: {relative_path}")

        reference_art = raw_companion.get("referenceArt")
        if reference_art is not None:
            if not isinstance(reference_art, dict):
                errors.append(f"companion {companion_id or index} referenceArt must be an object")
            else:
                source_status = str(reference_art.get("sourceStatus") or "")
                if not source_status.strip():
                    errors.append(f"companion {companion_id or index} referenceArt missing sourceStatus")
                expected_path = reference_art.get("expectedSourcePath")
                if expected_path is not None and not _is_safe_relative_path(str(expected_path)):
                    errors.append(f"companion {companion_id or index} has unsafe referenceArt.expectedSourcePath")
                source_image_path = reference_art.get("sourceImagePath")
                if source_image_path is not None and not _asset_exists(roster_dir, str(source_image_path)):
                    errors.append(f"companion {companion_id or index} missing referenceArt.sourceImagePath: {source_image_path}")
                chat_image_order = reference_art.get("chatImageOrder")
                if chat_image_order is not None and not isinstance(chat_image_order, int):
                    errors.append(f"companion {companion_id or index} referenceArt.chatImageOrder must be an integer")
                canonical_notes = reference_art.get("canonicalDesignNotes")
                if canonical_notes is not None and (
                    not isinstance(canonical_notes, list)
                    or not all(isinstance(note, str) and note.strip() for note in canonical_notes)
                ):
                    errors.append(f"companion {companion_id or index} referenceArt.canonicalDesignNotes must be non-empty strings")

        if str(raw_companion.get("artStatus") or "") in PLACEHOLDER_ART_STATUSES:
            warnings.append(f"companion {companion_id} uses placeholder art")

    if "koda" not in companion_ids:
        errors.append("roster must include koda as the default public companion")
    if len(companion_ids) < 6:
        errors.append("roster must include at least six public starter companions")

    return errors, warnings, roster


def main() -> int:
    repo = _repo_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default=repo / "hermes-agent-pets" / "companions.json", help="Roster JSON path.")
    parser.add_argument("--quiet", action="store_true", help="Only print errors.")
    args = parser.parse_args()

    path = Path(args.path).expanduser().resolve()
    errors, warnings, roster = validate_roster(path)
    if errors:
        print(f"Companion roster validation failed: {path}")
        for error in errors:
            print(f"error: {error}")
        for warning in warnings:
            print(f"warning: {warning}")
        return 1

    if not args.quiet:
        companions = roster.get("companions") if isinstance(roster.get("companions"), list) else []
        print(f"Companion roster validation passed: {path}")
        print(f"Companions: {', '.join(str(item.get('id')) for item in companions if isinstance(item, dict))}")
        for warning in warnings:
            print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
