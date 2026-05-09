"""Agent-native Hermes pet plugin."""

from __future__ import annotations

import hashlib
import atexit
import fcntl
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

STATE_DIR = Path.home() / ".hermes" / "hermes-pet-agent"
STATE_FILE = STATE_DIR / "state.json"
PLUGIN_DIR = Path(__file__).resolve().parent
REPO_ROOT = PLUGIN_DIR.parents[1] if len(PLUGIN_DIR.parents) > 1 else PLUGIN_DIR
PET_ASSET_ROOT = PLUGIN_DIR / "assets"
DEFAULT_PET_ID = "koda"
DEFAULT_PET_ASSET_DIR = PLUGIN_DIR / "assets" / DEFAULT_PET_ID
DEFAULT_PET_FILE = DEFAULT_PET_ASSET_DIR / "pet.json"
DEFAULT_SPRITESHEET_FILE = DEFAULT_PET_ASSET_DIR / "spritesheet.webp"
DEFAULT_STOP_POSE_FILE = DEFAULT_PET_ASSET_DIR / "guard-peek-stop-no-panel.png"
DEFAULT_STOP_RUN_POSE_FILE = DEFAULT_PET_ASSET_DIR / "stop-sign-run-front-strip.png"
HERMES_PET_STATES = (
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
HERMES_STATE_OVERLAY_FALLBACKS = {
    "idle": "idle",
    "thinking": "waiting",
    "working": "running",
    "success": "success",
    "blocked": "stop-sign",
    "error": "failed",
    "sleeping": "idle",
    "reminding": "waving",
    "learning": "review",
    "recalling": "review",
}
HERMES_MOOD_TO_STATE = {
    "idle": "idle",
    "thinking": "thinking",
    "waiting": "thinking",
    "running": "working",
    "approved": "working",
    "succeeded": "success",
    "success": "success",
    "done": "success",
    "stop-sign": "blocked",
    "blocked": "blocked",
    "failed": "error",
    "error": "error",
    "sleeping": "sleeping",
    "reminding": "reminding",
    "learning": "learning",
    "review": "learning",
    "reviewing": "learning",
    "recalling": "recalling",
}


class HermesPetStateManager:
    """Small adapter for mapping Hermes concepts onto current overlay states."""

    supported_states = HERMES_PET_STATES
    overlay_fallbacks = HERMES_STATE_OVERLAY_FALLBACKS

    @classmethod
    def normalize(cls, value: str) -> str:
        mood = (value or "idle").lower()
        return HERMES_MOOD_TO_STATE.get(mood, mood if mood in cls.supported_states else "idle")

    @classmethod
    def overlay_state(cls, value: str) -> str:
        return cls.overlay_fallbacks.get(cls.normalize(value), "idle")


def _overlay_executable() -> Path:
    env_path = os.environ.get("HERMES_PET_OVERLAY_EXE")
    candidates = []
    if env_path:
        candidates.append(Path(env_path).expanduser())
    candidates.extend(
        [
            PLUGIN_DIR / "bin" / "hermes-pet-overlay",
            PLUGIN_DIR / "HermesPetOverlay.app" / "Contents" / "MacOS" / "hermes-pet-overlay",
            REPO_ROOT / "build" / "HermesPetOverlay.app" / "Contents" / "MacOS" / "hermes-pet-overlay",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


OVERLAY_EXE = _overlay_executable()
OVERLAY_STATE_FILE = STATE_DIR / "overlay-state"
OVERLAY_AWAKE_FILE = STATE_DIR / "overlay-awake"
OVERLAY_MODE_FILE = STATE_DIR / "overlay-mode"
OVERLAY_POSITION_FILE = STATE_DIR / "overlay-position"
OVERLAY_PID_FILE = STATE_DIR / "overlay.pid"
OVERLAY_OWNER_FILE = STATE_DIR / "overlay-owner.pid"
OVERLAY_LOCK_FILE = STATE_DIR / "overlay.lock"
CONFIRM_LOCK_FILE = STATE_DIR / "confirm-delete.lock"
OVERLAY_HEARTBEAT_FILE = STATE_DIR / f"overlay-heartbeat-{os.getpid()}"
DECISION_DIR = STATE_DIR / "decisions"
_HEARTBEAT_STARTED = False
_CLEANUP_REGISTERED = False
FAILURE_THRESHOLD = 3
APPROVAL_SECONDS = 300
DENIAL_SECONDS = 120
DENIAL_REPROMPT_COOLDOWN_SECONDS = 12
HEARTBEAT_INTERVAL = 0.08
OVERLAY_HEARTBEAT_TIMEOUT = 0.35
CONFIRM_SECONDS = float(os.environ.get("HERMES_PET_CONFIRM_SECONDS", "45"))

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
PYTHON_STRING_ASSIGNMENT_PATTERN = re.compile(r"\b(?P<name>[A-Za-z_]\w*)\s*=\s*['\"](?P<value>[^'\"]+)['\"]")
PYTHON_VAR_DELETION_PATTERN = re.compile(
    r"\b(?:os|pathlib|shutil)\.(?:remove|unlink|rmtree|rmdir)\s*\(\s*(?P<name>[A-Za-z_]\w*)\s*\)|\b(?:Path|PosixPath)\s*\(\s*(?P<path_name>[A-Za-z_]\w*)\s*\)\.(?:unlink|rmdir)\s*\(",
    re.IGNORECASE,
)
UNKNOWN_DELETION_TARGET = "Python deletion call"
GLOBAL_DENIAL_KEY = "*"


def _overlay_enabled_for_process() -> bool:
    argv = [str(part).lower() for part in sys.argv]
    return "gateway" not in argv


def _safe_pet_id(value: str) -> str:
    pet_id = (value or DEFAULT_PET_ID).strip().lower()
    return pet_id if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", pet_id) else DEFAULT_PET_ID


def _pet_asset_dir(pet_id: str) -> Path:
    return PET_ASSET_ROOT / _safe_pet_id(pet_id)


def _pet_is_packaged(pet_id: str) -> bool:
    asset_dir = _pet_asset_dir(pet_id)
    return (asset_dir / "pet.json").is_file() and (asset_dir / "spritesheet.webp").is_file()


def _active_pet_id(state: Optional[Dict[str, Any]] = None) -> str:
    state = state or _load()
    pet_id = _safe_pet_id(str(state.get("active_pet") or DEFAULT_PET_ID))
    return pet_id if _pet_is_packaged(pet_id) else DEFAULT_PET_ID


def _active_pet_asset_dir(state: Optional[Dict[str, Any]] = None) -> Path:
    return _pet_asset_dir(_active_pet_id(state))


def _pet_manifest(pet_id: str) -> Dict[str, Any]:
    try:
        data = json.loads((_pet_asset_dir(pet_id) / "pet.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _pet_display_name(pet_id: str) -> str:
    manifest = _pet_manifest(pet_id)
    return str(manifest.get("displayName") or pet_id.title())


def _panel_shell_path(asset_dir: Path) -> str:
    panel_shell = asset_dir / "panel-shell.png"
    return str(panel_shell) if panel_shell.is_file() else ""


def _pet_dance_asset_paths(pet_id: str) -> tuple[Path, Path, Path]:
    asset_dir = _pet_asset_dir(pet_id)
    return (
        asset_dir / "dance-bob-strip.png",
        asset_dir / "dance-step-strip.png",
        asset_dir / "dance-hit-strip.png",
    )


def _pet_supports_dance(pet_id: str) -> bool:
    return all(path.is_file() for path in _pet_dance_asset_paths(pet_id))


def _default_state() -> Dict[str, Any]:
    return {
        "awake": False,
        "mood": "sleeping",
        "dance_enabled": False,
        "active_pet": DEFAULT_PET_ID,
        "failure_count": 0,
        "pending_approvals": {},
        "denied_approvals": {},
        "last_event": "Hermes pet is asleep.",
        "updated_at": time.time(),
    }


def _load() -> Dict[str, Any]:
    try:
        data = json.loads(STATE_FILE.read_text())
    except Exception:
        data = _default_state()
    base = _default_state()
    base.update(data if isinstance(data, dict) else {})
    if not isinstance(base.get("pending_approvals"), dict):
        base["pending_approvals"] = {}
    if not isinstance(base.get("denied_approvals"), dict):
        base["denied_approvals"] = {}
    base["dance_enabled"] = bool(base.get("dance_enabled"))
    if not _pet_asset_dir(str(base.get("active_pet") or DEFAULT_PET_ID)).is_dir():
        base["active_pet"] = DEFAULT_PET_ID
    return base


def _save(state: Dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = time.time()
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def _heartbeat_loop() -> None:
    while True:
        try:
            if not _overlay_enabled_for_process():
                time.sleep(HEARTBEAT_INTERVAL)
                continue
            state = _load()
            if state.get("awake"):
                STATE_DIR.mkdir(parents=True, exist_ok=True)
                OVERLAY_HEARTBEAT_FILE.write_text(f"{time.time():.6f}\n")
                if not _overlay_running():
                    _overlay_launch(_launch_state_for_mood(str(state.get("mood") or "idle")))
        except Exception:
            pass
        time.sleep(HEARTBEAT_INTERVAL)


def _start_heartbeat() -> None:
    global _HEARTBEAT_STARTED
    if not _overlay_enabled_for_process():
        return
    if _HEARTBEAT_STARTED:
        return
    _HEARTBEAT_STARTED = True
    thread = threading.Thread(target=_heartbeat_loop, name="hermes-pet-overlay-heartbeat", daemon=True)
    thread.start()


def _cleanup_stale_overlay_files() -> None:
    try:
        for path in STATE_DIR.glob("overlay-heartbeat*"):
            if path != OVERLAY_HEARTBEAT_FILE:
                path.unlink(missing_ok=True)
    except Exception:
        pass


def _overlay_pid() -> Optional[int]:
    try:
        return int(OVERLAY_PID_FILE.read_text().strip())
    except Exception:
        return None


def _overlay_running() -> bool:
    pid = _overlay_pid()
    if not pid:
        return False
    try:
        reaped, _status = os.waitpid(pid, os.WNOHANG)
        if reaped == pid:
            try:
                OVERLAY_PID_FILE.unlink()
            except FileNotFoundError:
                pass
            return False
    except ChildProcessError:
        pass
    except OSError:
        pass
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        try:
            OVERLAY_PID_FILE.unlink()
        except FileNotFoundError:
            pass
        return False
    except Exception:
        return False


def _overlay_owner_pid() -> Optional[int]:
    try:
        return int(OVERLAY_OWNER_FILE.read_text().strip())
    except Exception:
        return None


def _overlay_send(overlay_state: str, message: str = "") -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    clean_message = " ".join(str(message or "").split())[:80]
    OVERLAY_STATE_FILE.write_text(f"{overlay_state} {time.time():.6f} {clean_message}\n")


def _truthy_env(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _front_window_anchor_enabled() -> bool:
    if _truthy_env("HERMES_PET_DISABLE_FRONT_WINDOW_ANCHOR"):
        return False
    raw = os.environ.get("HERMES_PET_ANCHOR_TO_FRONT_WINDOW")
    if raw is None:
        raw = os.environ.get("HERMES_PET_ANCHOR_FRONT_WINDOW")
    if raw is None:
        return True
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def _dance_enabled_for_state(state: Optional[Dict[str, Any]] = None) -> bool:
    if _truthy_env("HERMES_PET_DANCE_ON_BY_DEFAULT"):
        return True
    if state is None:
        state = _load()
    return bool(state.get("dance_enabled")) and _pet_supports_dance(_active_pet_id(state))


def _spawn_detached_overlay(args: list[str]) -> bool:
    try:
        process = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        OVERLAY_PID_FILE.write_text(f"{process.pid}\n")
    except Exception:
        return False
    return True


def _overlay_launch(initial_state: str = "idle") -> bool:
    if not _overlay_enabled_for_process():
        return False
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with OVERLAY_LOCK_FILE.open("a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        _cleanup_stale_overlay_files()
        if _overlay_running():
            if _overlay_owner_pid() != os.getpid():
                _overlay_stop()
            else:
                active_pet_name = _pet_display_name(_active_pet_id(_load()))
                OVERLAY_HEARTBEAT_FILE.write_text(f"{time.time():.6f}\n")
                _start_heartbeat()
                _register_overlay_cleanup()
                _overlay_send(initial_state, _bubble_message_for_state({"mood": initial_state, "last_event": f"{active_pet_name} is awake."}))
                return True
        OVERLAY_AWAKE_FILE.touch()
        OVERLAY_HEARTBEAT_FILE.write_text(f"{time.time():.6f}\n")
        _start_heartbeat()
        _register_overlay_cleanup()
        if _overlay_running():
            active_pet_name = _pet_display_name(_active_pet_id(_load()))
            _overlay_send(initial_state, _bubble_message_for_state({"mood": initial_state, "last_event": f"{active_pet_name} is awake."}))
            return True
        if not OVERLAY_EXE.exists():
            return False
        state = _load()
        active_pet = _active_pet_id(state)
        active_pet_name = _pet_display_name(active_pet)
        active_asset_dir = _active_pet_asset_dir(state)
        spritesheet = active_asset_dir / "spritesheet.webp"
        stop_pose = active_asset_dir / "guard-peek-stop-no-panel.png"
        stop_run_pose = active_asset_dir / "stop-sign-run-front-strip.png"
        args = [
            str(OVERLAY_EXE),
            "--hermes-agent",
            "--spritesheet", str(spritesheet),
            "--pet-name", active_pet_name,
            "--stop-pose", str(stop_pose) if stop_pose.is_file() else "",
            "--stop-run-pose", str(stop_run_pose) if stop_run_pose.is_file() else "",
            "--panel-shell", str(_panel_shell_path(active_asset_dir)),
            "--state", initial_state,
            "--state-file", str(OVERLAY_STATE_FILE),
            "--awake-file", str(OVERLAY_AWAKE_FILE),
            "--mode-file", str(OVERLAY_MODE_FILE),
            "--position-file", str(OVERLAY_POSITION_FILE),
            "--owner-pid", str(os.getpid()),
            "--heartbeat-file", str(OVERLAY_HEARTBEAT_FILE),
            "--heartbeat-timeout", f"{OVERLAY_HEARTBEAT_TIMEOUT:.2f}",
            "--main-screen-only",
            "--clickable",
            "--no-activity-monitor",
            "--scale", "0.42",
            "--margin", "32",
        ]
        if _dance_enabled_for_state(state):
            dance_bob, dance_step, dance_hit = _pet_dance_asset_paths(active_pet)
            args.extend([
                "--dance-bob", str(dance_bob),
                "--dance-step", str(dance_step),
                "--dance-hit", str(dance_hit),
            ])
            args.append("--audio-reactive")
        if _front_window_anchor_enabled():
            args.append("--anchor-front-window")
        try:
            OVERLAY_PID_FILE.unlink()
        except FileNotFoundError:
            pass
        if not _spawn_detached_overlay(args):
            return False
        OVERLAY_OWNER_FILE.write_text(f"{os.getpid()}\n")
        time.sleep(0.05)
        _overlay_send(initial_state, _bubble_message_for_state({"mood": initial_state, "last_event": f"{active_pet_name} is awake."}))
        return True


def _overlay_stop() -> None:
    try:
        OVERLAY_AWAKE_FILE.unlink()
    except FileNotFoundError:
        pass
    _overlay_send("idle")
    pid = _overlay_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    try:
        OVERLAY_PID_FILE.unlink()
    except FileNotFoundError:
        pass
    try:
        OVERLAY_OWNER_FILE.unlink()
    except FileNotFoundError:
        pass
    try:
        OVERLAY_HEARTBEAT_FILE.unlink()
    except FileNotFoundError:
        pass


def _register_overlay_cleanup() -> None:
    global _CLEANUP_REGISTERED
    if _CLEANUP_REGISTERED:
        return
    _CLEANUP_REGISTERED = True
    atexit.register(_overlay_stop)


def _overlay_confirm_delete(code: str, deletion: str) -> str:
    if not _overlay_running():
        _overlay_launch("idle")
    DECISION_DIR.mkdir(parents=True, exist_ok=True)
    decision_file = DECISION_DIR / f"delete-{code}.decision"
    try:
        decision_file.unlink()
    except FileNotFoundError:
        pass
    _overlay_send(f"confirm-delete {decision_file}", f"delete {Path(deletion).name}?")
    deadline = time.time() + CONFIRM_SECONDS
    while time.time() < deadline:
        try:
            decision = decision_file.read_text().strip().lower()
        except Exception:
            decision = ""
        if decision in {"approve", "cancel"}:
            try:
                decision_file.unlink()
            except FileNotFoundError:
                pass
            return decision
        if not _load().get("awake"):
            return "cancel"
        time.sleep(0.15)
    return "timeout"


def _approve_hermes_delete_command(command: str) -> None:
    try:
        from tools.approval import (
            approve_session,
            detect_dangerous_command,
            get_current_session_key,
        )

        is_dangerous, pattern_key, _description = detect_dangerous_command(command)
        if is_dangerous and pattern_key:
            approve_session(get_current_session_key(), pattern_key)
    except Exception:
        pass


def _overlay_state_for_mood(mood: str) -> str:
    return HermesPetStateManager.overlay_state(mood)


def _launch_state_for_mood(mood: str) -> str:
    overlay_state = _overlay_state_for_mood(mood)
    return "idle" if overlay_state == "stop-sign" else overlay_state


def _bubble_message_for_state(state: Dict[str, Any]) -> str:
    mood = str(state.get("mood") or "idle").lower()
    event = " ".join(str(state.get("last_event") or "").split())
    if mood in {"thinking", "waiting"}:
        if event.startswith("Thinking about:"):
            subject = event.split(":", 1)[1].strip()
            return f"thinking: {subject}" if subject else "thinking..."
        return "thinking..."
    if mood in {"running", "approved"}:
        if event.startswith("Running tool:"):
            tool = event.split(":", 1)[1].strip()
            return f"running {tool}" if tool else "working..."
        if event.startswith("Approved deletion"):
            return "deleting..."
        return "working..."
    if mood == "failed":
        return "that failed"
    if mood in {"succeeded", "success", "done"}:
        return "success"
    if mood == "stop-sign":
        return "pause"
    if mood in {"review", "reviewing"}:
        return "checking..."
    return ""


def _save_and_sync(state: Dict[str, Any]) -> None:
    _save(state)
    if not _overlay_enabled_for_process():
        return
    if not state.get("awake"):
        _overlay_stop()
        return
    overlay_state = _overlay_state_for_mood(str(state.get("mood") or "idle"))
    if not _overlay_running():
        _overlay_launch(_launch_state_for_mood(str(state.get("mood") or "idle")))
        if overlay_state == "stop-sign":
            return
    _overlay_send(overlay_state, _bubble_message_for_state(state))


def _set(mood: str, event: str) -> None:
    state = _load()
    state["mood"] = mood
    state["last_event"] = event
    _save_and_sync(state)


def _command(args: Dict[str, Any]) -> str:
    value = (
        args.get("command")
        or args.get("cmd")
        or args.get("input")
        or args.get("text")
        or args.get("query")
        or args.get("code")
        or ""
    )
    if value:
        return str(value)
    try:
        return json.dumps(args, sort_keys=True)
    except Exception:
        return str(args)


def _is_dangerous(command: str) -> bool:
    normalized = " ".join(command.lower().split())
    return any(re.search(pattern, normalized) for pattern in DANGEROUS_PATTERNS)


def _deletion_path(command: str) -> Optional[str]:
    normalized = " ".join(command.split())
    try:
        tokens = shlex.split(normalized)
    except ValueError:
        tokens = []
    if tokens and tokens[0] in {"rm", "delete", "unlink"}:
        for token in tokens[1:]:
            if token.startswith("-"):
                continue
            return token

    match = DELETION_PATTERN.search(normalized)
    if match:
        return match.group("path")

    match = PYTHON_DELETION_PATTERN.search(command)
    if match:
        return match.group("path")

    match = PYTHON_PATH_UNLINK_PATTERN.search(command)
    if match:
        return match.group("path")

    assignments = {m.group("name"): m.group("value") for m in PYTHON_STRING_ASSIGNMENT_PATTERN.finditer(command)}
    match = PYTHON_VAR_DELETION_PATTERN.search(command)
    if match:
        variable_name = match.group("name") or match.group("path_name")
        if variable_name in assignments:
            return assignments[variable_name]

    if PYTHON_DELETION_CALL_PATTERN.search(command):
        return UNKNOWN_DELETION_TARGET

    return None


def _code_for(command: str) -> str:
    return hashlib.sha256(command.encode("utf-8")).hexdigest()[:8]


def _denial_keys(command: str, deletion: str) -> set[str]:
    keys = {_code_for(command)}
    if deletion:
        keys.add(f"path:{deletion}")
        try:
            keys.add(f"path:{str(Path(deletion).expanduser().resolve(strict=False))}")
        except Exception:
            pass
    return keys


def _cleanup_approvals(state: Dict[str, Any]) -> None:
    now = time.time()
    pending = state.get("pending_approvals") or {}
    state["pending_approvals"] = {
        code: item for code, item in pending.items()
        if isinstance(item, dict) and float(item.get("expires_at", 0)) > now
    }
    denied = state.get("denied_approvals") or {}
    state["denied_approvals"] = {
        code: item for code, item in denied.items()
        if isinstance(item, dict) and float(item.get("expires_at", 0)) > now
    }


def _is_failed(result: str) -> bool:
    text = result or ""
    lowered = text.lower()
    if (
        "hermes pet denied deletion" in lowered
        or "hermes pet cancelled" in lowered
        or "hermes pet is already handling deletion" in lowered
    ):
        return False
    try:
        data = json.loads(text)
    except Exception:
        data = None
    if isinstance(data, dict):
        if isinstance(data.get("exit_code"), int) and data["exit_code"] != 0:
            return True
        if data.get("error"):
            return True
        if str(data.get("status") or "").lower() in {"error", "failed", "failure"}:
            return True
    return any(marker in lowered for marker in ('"error"', "traceback", "timed out", "timeout"))


def _stop_sign(title: str, body: str) -> str:
    return (
        "\n"
        "        █████████████████\n"
        "     ███                 ███\n"
        "   ██        STOP          ██\n"
        "     ███                 ███\n"
        "        █████████████████\n\n"
        f"Hermes pet: {title}\n{body}"
    )


def _denied_delete_message(deletion: str) -> str:
    return (
        f"Hermes pet denied deletion of `{deletion}`. "
        "The user explicitly clicked Cancel, so this destructive action is not approved. "
        "Do not retry it, rename the file to bypass review, use Python/os.remove, unlink, rmtree, or suggest a workaround. "
        "Report that the deletion was cancelled by the user."
    )


def _roster_candidates() -> list[Path]:
    return [
        PLUGIN_DIR.parent / "companions.json",
        PLUGIN_DIR / "companions.json",
        REPO_ROOT / "hermes-agent-pets" / "companions.json",
    ]


def _load_companion_roster() -> Dict[str, Any]:
    for path in _roster_candidates():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and isinstance(data.get("companions"), list):
            return data
    return {"companions": []}


def _companion_roster_card() -> str:
    roster = _load_companion_roster()
    companions = [item for item in roster.get("companions", []) if isinstance(item, dict)]
    if not companions:
        return "No Hermes companion roster found."

    state = _load()
    active_pet = _active_pet_id(state)
    lines = [
        "Hermes companions",
        f"active: {_pet_display_name(active_pet)} ({active_pet})",
        f"states: {', '.join(HermesPetStateManager.supported_states)}",
        "",
    ]
    for item in companions:
        companion_id = str(item.get("id") or "?")
        name = str(item.get("name") or companion_id)
        role = str(item.get("hermesRole") or "companion")
        art_status = str(item.get("artStatus") or "unknown art")
        usable = "usable" if _pet_is_packaged(companion_id) else "reference"
        marker = " [active]" if companion_id == active_pet else ""
        lines.append(f"- {name} ({companion_id}): {role}; art: {art_status}; {usable}{marker}")
    lines.append("")
    lines.append("Use /pet companion <id> to switch to a packaged companion.")
    return "\n".join(lines)


def _pet_card(state: Dict[str, Any], title: str = "Hermes Pet") -> str:
    active_pet = _active_pet_id(state)
    active_pet_name = _pet_display_name(active_pet)
    awake = "awake" if state.get("awake") else "asleep"
    mood = state.get("mood") or "idle"
    dance = "on" if _dance_enabled_for_state(state) else "off"
    pending = len(state.get("pending_approvals") or {})
    last = state.get("last_event") or "No recent activity."
    return (
        f"{active_pet_name} — {title}\n"
        f"state: {awake} | pet: {active_pet} | mood: {mood} | dance: {dance} | failures: {state.get('failure_count', 0)} | pending: {pending}\n"
        f"last: {last}\n"
    )


def _handle_pet(raw_args: str = "") -> str:
    argv = (raw_args or "").strip().split()
    action = (argv[0] if argv else "wake").lower()
    state = _load()
    _cleanup_approvals(state)

    if action in {"wake", "up", "start"}:
        _overlay_stop()
        pet_name = _pet_display_name(_active_pet_id(state))
        state["awake"] = True
        state["mood"] = "idle"
        state["failure_count"] = 0
        state["last_event"] = f"{pet_name} is awake and watching Hermes."
        _save_and_sync(state)
        return _pet_card(state, "awake and watching Hermes")

    if action in {"sleep", "down", "stop"}:
        pet_name = _pet_display_name(_active_pet_id(state))
        state["awake"] = False
        state["mood"] = "sleeping"
        state["failure_count"] = 0
        state["last_event"] = f"{pet_name} is asleep."
        _save_and_sync(state)
        return _pet_card(state, "asleep")

    if action == "status":
        pending = state.get("pending_approvals") or {}
        awake = "awake" if state.get("awake") else "asleep"
        if state.get("awake"):
            _overlay_launch(_launch_state_for_mood(str(state.get("mood") or "idle")))
        return _pet_card(state, "status")

    if action in {"use", "switch", "select"} or (action in {"companion", "pet"} and len(argv) > 1):
        requested = argv[1] if action in {"companion", "pet"} and len(argv) > 1 else (argv[1] if len(argv) > 1 else "")
        pet_id = _safe_pet_id(requested)
        if not requested:
            return "Usage: /pet companion <id>"
        if not _pet_is_packaged(pet_id):
            return f"{requested} is not packaged as a usable Hermes pet yet. Run /pet companions to see available pets."
        state["active_pet"] = pet_id
        state["last_event"] = f"Switched active companion to {_pet_display_name(pet_id)}."
        if state.get("awake"):
            _overlay_stop()
        _save_and_sync(state)
        return _pet_card(state, f"using {_pet_display_name(pet_id)}")

    if action in {"companions", "companion", "roster", "pets"}:
        return _companion_roster_card()

    if action in {"dance", "dancing"}:
        choice = (argv[1] if len(argv) > 1 else "status").lower()
        if choice in {"on", "enable", "enabled", "yes", "true", "1"}:
            active_pet = _active_pet_id(state)
            if not _pet_supports_dance(active_pet):
                state["dance_enabled"] = False
                state["last_event"] = f"Audio-reactive dancing is not available for {_pet_display_name(active_pet)} yet."
                _save_and_sync(state)
                return _pet_card(state, "dance unavailable")
            state["dance_enabled"] = True
            state["last_event"] = "Audio-reactive dancing is enabled."
            if state.get("awake"):
                _overlay_stop()
            _save_and_sync(state)
            return _pet_card(state, "dance enabled")
        if choice in {"off", "disable", "disabled", "no", "false", "0"}:
            state["dance_enabled"] = False
            if state.get("mood") == "dancing":
                state["mood"] = "idle"
            state["last_event"] = "Audio-reactive dancing is disabled."
            if state.get("awake"):
                _overlay_stop()
            _save_and_sync(state)
            return _pet_card(state, "dance disabled")
        if choice == "status":
            return _pet_card(state, "dance status")
        return "Usage: /pet dance [on|off|status]"

    if action in {"stop-sign", "stop", "halt"}:
        state["mood"] = "stop-sign"
        state["last_event"] = "Manual stop sign triggered."
        _save_and_sync(state)
        return _stop_sign("Manual stop sign", "Hermes pet is asking you to pause before continuing.")

    if action == "approve":
        if len(argv) < 2:
            return "Usage: /pet approve <code>"
        code = argv[1]
        item = (state.get("pending_approvals") or {}).get(code)
        if not item:
            _save_and_sync(state)
            return f"No pending Hermes pet approval for code {code}."
        item["approved"] = True
        item["expires_at"] = time.time() + APPROVAL_SECONDS
        state["pending_approvals"][code] = item
        state["mood"] = "approved"
        state["last_event"] = f"Approved deletion code {code}. Ask Hermes to retry the command."
        _save_and_sync(state)
        return f"Hermes pet approved code {code}. Ask Hermes to retry the deletion now."

    if action == "cancel":
        if len(argv) < 2:
            return "Usage: /pet cancel <code>"
        code = argv[1]
        removed = (state.get("pending_approvals") or {}).pop(code, None)
        state["mood"] = "idle"
        state["last_event"] = f"Cancelled deletion code {code}."
        _save_and_sync(state)
        return f"Hermes pet cancelled code {code}." if removed else f"No pending Hermes pet approval for code {code}."

    return "Usage: /pet [wake|sleep|status|companions|companion <id>|dance on|dance off|stop-sign|approve <code>|cancel <code>]"


def _on_pre_tool_call(tool_name: str, args: Dict[str, Any], **kwargs):
    if not _overlay_enabled_for_process():
        return None
    state = _load()
    _cleanup_approvals(state)
    if not state.get("awake") or tool_name not in WATCHED_TOOLS:
        _save_and_sync(state)
        return None

    command = _command(args) if tool_name in COMMAND_TOOLS else ""
    if command and _is_dangerous(command):
        state["mood"] = "stop-sign"
        state["last_event"] = f"Blocked dangerous command: {command}"
        _save_and_sync(state)
        return {"action": "block", "message": _stop_sign("Dangerous command blocked", f"Command: `{command}`")}

    deletion = _deletion_path(command) if command else None
    if deletion:
        CONFIRM_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        with CONFIRM_LOCK_FILE.open("a+") as lock_file:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"action": "block", "message": f"Hermes pet is already handling deletion of `{deletion}`. Do not start a second deletion attempt or bypass the Hermes pet."}
            try:
                state = _load()
                _cleanup_approvals(state)
                code = _code_for(command)
                now = time.time()
                denied = state.setdefault("denied_approvals", {})
                global_denial = denied.get(GLOBAL_DENIAL_KEY)
                if isinstance(global_denial, dict) and float(global_denial.get("expires_at", 0)) > now:
                    state["mood"] = "idle"
                    state["failure_count"] = 0
                    state["last_event"] = f"Denied deletion during cancel cooldown: {deletion}"
                    _save_and_sync(state)
                    return {"action": "block", "message": _denied_delete_message(deletion)}
                denied_item = next((denied.get(key) for key in _denial_keys(command, deletion) if isinstance(denied.get(key), dict)), None)
                if isinstance(denied_item, dict):
                    if float(denied_item.get("expires_at", 0)) > now:
                        state["mood"] = "idle"
                        state["failure_count"] = 0
                        state["last_event"] = f"Denied deletion approval {code}: {deletion}"
                        _save_and_sync(state)
                        return {"action": "block", "message": _denied_delete_message(deletion)}
                    for key in _denial_keys(command, deletion):
                        denied.pop(key, None)
                pending = state.setdefault("pending_approvals", {})
                item = pending.get(code)
                if isinstance(item, dict) and item.get("approved") and float(item.get("expires_at", 0)) > now:
                    pending.pop(code, None)
                    state["mood"] = "running"
                    state["last_event"] = f"Approved deletion is running: {deletion}"
                    _save_and_sync(state)
                    return None
                pending[code] = {
                    "command": command,
                    "path": deletion,
                    "approved": False,
                    "expires_at": now + APPROVAL_SECONDS,
                }
                state["mood"] = "stop-sign"
                state["last_event"] = f"Waiting for deletion approval {code}: {deletion}"
                _save_and_sync(state)
                decision = _overlay_confirm_delete(code, deletion)
                if decision == "approve":
                    _approve_hermes_delete_command(command)
                    pending.pop(code, None)
                    state["mood"] = "running"
                    state["last_event"] = f"Approved deletion is running: {deletion}"
                    _save_and_sync(state)
                    return None
                if decision == "cancel":
                    pending.pop(code, None)
                    denied_until = time.time() + DENIAL_SECONDS
                    denied[GLOBAL_DENIAL_KEY] = {
                        "command": command,
                        "path": deletion,
                        "expires_at": time.time() + DENIAL_REPROMPT_COOLDOWN_SECONDS,
                    }
                    for key in _denial_keys(command, deletion):
                        denied[key] = {
                            "command": command,
                            "path": deletion,
                            "expires_at": denied_until,
                        }
                    state["mood"] = "idle"
                    state["failure_count"] = 0
                    state["last_event"] = f"Cancelled deletion approval {code}: {deletion}"
                    _save_and_sync(state)
                    return {"action": "block", "message": _denied_delete_message(deletion)}
                return {
                    "action": "block",
                    "message": _stop_sign(
                        "Are you sure?",
                        f"Hermes wants to delete `{deletion}`.\nClick Delete in the Hermes pet prompt, or approve with `/pet approve {code}` and retry.\nCancel with `/pet cancel {code}`.",
                    ),
                }
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    state["mood"] = "running"
    state["last_event"] = f"Running tool: {tool_name}"
    _save_and_sync(state)
    return None


def _on_pre_llm_call(user_message: str = "", **kwargs):
    if not _overlay_enabled_for_process():
        return None
    state = _load()
    _cleanup_approvals(state)
    if not state.get("awake"):
        _save_and_sync(state)
        return None
    snippet = " ".join(str(user_message or "").split())[:120]
    state["mood"] = "thinking"
    state["last_event"] = f"Thinking about: {snippet}" if snippet else "Thinking."
    _save_and_sync(state)
    return None


def _on_post_llm_call(assistant_response: str = "", **kwargs):
    if not _overlay_enabled_for_process():
        return None
    state = _load()
    _cleanup_approvals(state)
    if not state.get("awake"):
        _save_and_sync(state)
        return None
    if str(state.get("mood") or "").lower() in {"succeeded", "success", "done"}:
        state["failure_count"] = 0
    elif state.get("mood") != "stop-sign":
        state["mood"] = "idle"
        state["failure_count"] = 0
    state["last_event"] = "Answer finished."
    _save_and_sync(state)
    return None


def _on_post_tool_call(tool_name: str, args: Dict[str, Any], result: str, **kwargs):
    if not _overlay_enabled_for_process():
        return None
    state = _load()
    _cleanup_approvals(state)
    if not state.get("awake") or tool_name not in WATCHED_TOOLS:
        _save_and_sync(state)
        return None

    failed = _is_failed(result)
    if failed:
        count = int(state.get("failure_count") or 0) + 1
        state["failure_count"] = count
        if count >= FAILURE_THRESHOLD:
            state["mood"] = "stop-sign"
            state["last_event"] = f"Tool failed {count} times in a row: {tool_name}"
        else:
            state["mood"] = "failed"
            state["last_event"] = f"Tool failed: {tool_name}"
    else:
        state["failure_count"] = 0
        lowered_result = (result or "").lower()
        if "hermes pet denied deletion" in lowered_result:
            state["mood"] = "idle"
            state["last_event"] = "Deletion cancelled by Hermes pet."
        elif "hermes pet is already handling deletion" in lowered_result:
            state["mood"] = "idle"
            state["last_event"] = "Hermes pet kept one deletion confirmation active."
        else:
            state["mood"] = "succeeded"
            state["last_event"] = f"Tool finished: {tool_name}"
    _save_and_sync(state)
    return None


def register(ctx) -> None:
    ctx.register_command(
        "pet",
        handler=_handle_pet,
        description="Control agent-native Hermes pets.",
        args_hint="wake|sleep|status|companions|companion <id>|dance on|dance off|stop-sign|approve <code>|cancel <code>",
    )
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_hook("post_llm_call", _on_post_llm_call)
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    ctx.register_hook("post_tool_call", _on_post_tool_call)
