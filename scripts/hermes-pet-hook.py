#!/usr/bin/env python3
"""Hermes shell hook bridge for the Hermes pet desktop overlay."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


HERMES_PET_CTL = Path(os.environ.get("HERMES_PET_CTL", Path(__file__).resolve().with_name("hermes-pet")))
AWAKE_FILE = Path(os.environ.get("HERMES_PET_AWAKE_FILE", "/tmp/hermes-pet-overlay-awake"))
ACTIVE_DIR = Path(os.environ.get("HERMES_PET_HERMES_ACTIVE_DIR", "/tmp/hermes-pet-hermes-active"))
FAILURE_FILE = Path(os.environ.get("HERMES_PET_HERMES_FAILURE_FILE", "/tmp/hermes-pet-hermes-failures"))
STUCK_SECONDS = float(os.environ.get("HERMES_PET_HERMES_STUCK_SECONDS", "30"))
CONFIRM_SECONDS = float(os.environ.get("HERMES_PET_HERMES_CONFIRM_SECONDS", "45"))
CONFIRM_DIR = Path(os.environ.get("HERMES_PET_HERMES_CONFIRM_DIR", "/tmp/hermes-pet-hermes-confirm"))
DENIAL_SECONDS = float(os.environ.get("HERMES_PET_HERMES_DENIAL_SECONDS", "120"))

WATCHED_TOOLS = {
    "terminal",
    "terminal_command",
    "shell",
    "bash",
    "zsh",
    "exec_command",
    "execute_code",
    "python",
    "run_command",
    "process",
    "browser",
    "browser_open",
    "browser_click",
    "browser_type",
    "browser_snapshot",
    "browser_screenshot",
    "browser_wait",
    "web_extract",
    "web_crawl",
}

COMMAND_TOOLS = {
    "terminal",
    "terminal_command",
    "shell",
    "bash",
    "zsh",
    "exec_command",
    "execute_code",
    "python",
    "run_command",
    "process",
}

DANGEROUS_PATTERNS = [
    r"\brm\s+-[^\n;]*r[^\n;]*f[^\n;]*(?:/|~|\.)(?:\s|$|;)",
    r"\bsudo\s+rm\s+-[^\n;]*r[^\n;]*f\b",
    r"\bgit\s+push\b[^\n;]*(?:--force|-f)\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bchmod\s+-r\s+777\b",
    r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;:",
]

DELETION_PATTERN = re.compile(
    r"\b(?:rm|delete|unlink)\s+(?:-[^\n;]*\s+)*(?P<path>/tmp/[^\s;]+|/private/tmp/[^\s;]+|[^\s;]+)",
    re.IGNORECASE,
)
PYTHON_DELETION_PATTERN = re.compile(
    r"\b(?:os|pathlib|shutil)\.(?:remove|unlink|rmtree)\s*\(\s*['\"](?P<path>[^'\"]+)['\"]",
    re.IGNORECASE,
)
PYTHON_PATH_UNLINK_PATTERN = re.compile(
    r"\b(?:Path|PosixPath)\s*\(\s*['\"](?P<path>[^'\"]+)['\"]\s*\)\.unlink\s*\(",
    re.IGNORECASE,
)
PYTHON_DELETION_CALL_PATTERN = re.compile(
    r"\b(?:os|pathlib|shutil)\.(?:remove|unlink|rmtree|rmdir)\s*\(|\b(?:Path|PosixPath)\s*\([^)]+\)\.(?:unlink|rmdir)\s*\(",
    re.IGNORECASE,
)


def pet(state: str) -> None:
    if not AWAKE_FILE.exists():
        return
    try:
        subprocess.run(
            [str(HERMES_PET_CTL), state],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
    except Exception:
        pass


def pet_confirm_delete(decision_file: Path) -> None:
    if not AWAKE_FILE.exists():
        return
    try:
        subprocess.run(
            [str(HERMES_PET_CTL), "confirm-delete", str(decision_file)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
    except Exception:
        pass


def safe_id(payload: dict[str, Any]) -> str:
    extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
    raw = extra.get("tool_call_id") or payload.get("tool_call_id")
    if not raw:
        tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
        identity = {
            "session_id": extra.get("session_id") or payload.get("session_id") or "session",
            "tool_name": payload.get("tool_name") or "tool",
            "command": command_from(payload),
            "tool_input": tool_input,
        }
        stable = json.dumps(identity, sort_keys=True, default=str)
        digest = hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16]
        raw = f"{identity['session_id']}-{identity['tool_name']}-{digest}"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(raw))[:140]


def command_from(payload: dict[str, Any]) -> str:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    command = tool_input.get("command") or tool_input.get("cmd") or tool_input.get("code") or tool_input.get("input") or ""
    return str(command)


def is_dangerous(command: str) -> bool:
    normalized = " ".join(command.lower().split())
    return any(re.search(pattern, normalized) for pattern in DANGEROUS_PATTERNS)


def needs_delete_confirmation(command: str) -> bool:
    normalized = " ".join(command.split())
    try:
        tokens = shlex.split(normalized)
    except ValueError:
        tokens = []
    if tokens and tokens[0] in {"rm", "delete", "unlink"}:
        return any(not token.startswith("-") for token in tokens[1:])

    match = DELETION_PATTERN.search(normalized)
    if match and match.group("path"):
        return True
    return bool(
        PYTHON_DELETION_PATTERN.search(command)
        or PYTHON_PATH_UNLINK_PATTERN.search(command)
        or PYTHON_DELETION_CALL_PATTERN.search(command)
    )


def decision_path(command: str) -> Path:
    CONFIRM_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(command.encode("utf-8")).hexdigest()[:16]
    return CONFIRM_DIR / f"{digest}.decision"


def denial_path(command: str) -> Path:
    CONFIRM_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(command.encode("utf-8")).hexdigest()[:16]
    return CONFIRM_DIR / f"{digest}.denied"


def mark_denied(command: str) -> None:
    denial_path(command).write_text(f"{time.time() + DENIAL_SECONDS:.6f}\n")


def is_denied(command: str) -> bool:
    path = denial_path(command)
    try:
        expires_at = float(path.read_text().strip() or "0")
    except Exception:
        return False
    if expires_at > time.time():
        return True
    path.unlink(missing_ok=True)
    return False


def denied_delete_message() -> str:
    return (
        "Hermes pet denied the deletion. The user explicitly cancelled this destructive action. "
        "Do not retry it, rename the file to bypass review, use Python/os.remove, unlink, rmtree, or suggest a workaround. "
        "Report that the deletion was cancelled by the user."
    )


def wait_for_confirmation(command: str) -> str:
    path = decision_path(command)
    path.unlink(missing_ok=True)
    pet_confirm_delete(path)
    deadline = time.time() + CONFIRM_SECONDS
    while time.time() < deadline:
        if path.exists():
            decision = path.read_text(errors="ignore").strip().lower()
            path.unlink(missing_ok=True)
            if decision == "approve":
                return "approve"
            if decision == "cancel":
                mark_denied(command)
                return "cancel"
            return "timeout"
        if not AWAKE_FILE.exists():
            mark_denied(command)
            return "cancel"
        time.sleep(0.1)
    return "timeout"


def is_failed_result(result_text: str) -> bool:
    text = result_text or ""
    try:
        data = json.loads(text)
    except Exception:
        data = None

    if isinstance(data, dict):
        exit_code = data.get("exit_code")
        if isinstance(exit_code, int) and exit_code != 0:
            return True
        if data.get("error"):
            return True
        status = str(data.get("status") or "").lower()
        if status in {"error", "failed", "failure"}:
            return True

    lowered = text.lower()
    return bool(
        re.search(r"(?m)^traceback \(most recent call last\):", lowered)
        or re.search(r"(?m)^(error|failed|failure):\s+", lowered)
        or re.search(r"\b(?:command|operation|request)\s+timed out\b", lowered)
        or re.search(r"\btimed out after\s+\d", lowered)
        or re.search(r"\btimeout expired\b", lowered)
    )


def bump_failure_count(failed: bool) -> int:
    if not failed:
        FAILURE_FILE.write_text("0\n")
        return 0
    try:
        count = int(FAILURE_FILE.read_text().strip() or "0")
    except Exception:
        count = 0
    count += 1
    FAILURE_FILE.write_text(f"{count}\n")
    return count


def active_path(call_id: str) -> Path:
    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    return ACTIVE_DIR / f"{call_id}.json"


def start_watcher(path: Path) -> None:
    try:
        subprocess.Popen(
            [sys.executable, __file__, "--watch", str(path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        pass


def handle_pre(payload: dict[str, Any]) -> None:
    tool_name = str(payload.get("tool_name") or "")
    if tool_name not in WATCHED_TOOLS:
        return

    command = command_from(payload) if tool_name in COMMAND_TOOLS else ""
    if command and is_dangerous(command):
        pet("stop-sign")
        print(json.dumps({"action": "block", "message": "Hermes pet blocked this dangerous command."}))
        return
    if command and needs_delete_confirmation(command):
        if is_denied(command):
            pet("idle")
            print(json.dumps({"action": "block", "message": denied_delete_message()}))
            return
        decision = wait_for_confirmation(command)
        if decision == "approve":
            pet("running")
        elif decision == "cancel":
            pet("idle")
            print(json.dumps({"action": "block", "message": denied_delete_message()}))
            return
        else:
            pet("idle")
            print(json.dumps({"action": "block", "message": "Hermes pet did not approve the deletion. Do not retry or bypass this destructive action."}))
            return
    else:
        pet("running")

    path = active_path(safe_id(payload))
    path.write_text(json.dumps({"started_at": time.time(), "tool_name": tool_name}))
    start_watcher(path)


def handle_post(payload: dict[str, Any]) -> None:
    tool_name = str(payload.get("tool_name") or "")
    if tool_name not in WATCHED_TOOLS:
        return

    active_path(safe_id(payload)).unlink(missing_ok=True)
    extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
    failed = is_failed_result(str(extra.get("result") or ""))
    count = bump_failure_count(failed)
    if count >= 3:
        pet("stop-sign")
    elif failed:
        pet("failed")
    else:
        pet("success")


def watch(path: Path) -> None:
    time.sleep(STUCK_SECONDS)
    if path.exists():
        pet("stop-sign")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", type=Path)
    args = parser.parse_args()

    if args.watch is not None:
        watch(args.watch)
        return 0

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    if not isinstance(payload, dict):
        return 0

    event = str(payload.get("hook_event_name") or "")
    if event == "pre_tool_call":
        handle_pre(payload)
    elif event == "post_tool_call":
        handle_post(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
