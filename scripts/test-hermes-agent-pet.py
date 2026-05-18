#!/usr/bin/env python3
"""Run runtime regression checks for the Hermes pet package."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import ModuleType
from typing import Any

sys.dont_write_bytecode = True

PACKAGED_COMPANIONS = ("koda", "miko", "bramble", "nyx", "pip", "atlas")


class CheckFailure(AssertionError):
    pass


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def line(kind: str, label: str, detail: str = "") -> None:
    suffix = f": {detail}" if detail else ""
    print(f"{kind:4} {label}{suffix}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailure(message)


def import_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_plugin(plugin_dir: Path, home: Path) -> ModuleType:
    os.environ["HOME"] = str(home)
    os.environ["HERMES_PET_CONFIRM_SECONDS"] = "0.01"
    os.environ.pop("HERMES_PET_ANCHOR_TO_FRONT_WINDOW", None)
    os.environ.pop("HERMES_PET_ANCHOR_FRONT_WINDOW", None)
    os.environ.pop("HERMES_PET_DISABLE_FRONT_WINDOW_ANCHOR", None)
    os.environ.pop("HERMES_PET_DANCE_ON_BY_DEFAULT", None)
    name = f"hermes_pet_agent_test_{abs(hash((str(plugin_dir), time.time())))}"
    return import_module(plugin_dir / "__init__.py", name)


def patch_plugin_overlay(plugin: ModuleType) -> list[tuple[Any, ...]]:
    events: list[tuple[Any, ...]] = []

    def fake_launch(initial_state: str = "idle") -> bool:
        events.append(("launch", initial_state))
        return True

    def fake_stop() -> None:
        events.append(("stop",))

    def fake_running() -> bool:
        return True

    def fake_send(overlay_state: str, message: str = "") -> None:
        events.append(("send", overlay_state, message))
        plugin.STATE_DIR.mkdir(parents=True, exist_ok=True)
        plugin.OVERLAY_STATE_FILE.write_text(f"{overlay_state} {time.time():.6f} {message}\n")

    plugin._overlay_launch = fake_launch
    plugin._overlay_stop = fake_stop
    plugin._overlay_running = fake_running
    plugin._overlay_send = fake_send
    plugin._approve_hermes_delete_command = lambda command: events.append(("approve-command", command))
    return events


class FakeHermesContext:
    def __init__(self) -> None:
        self.commands: dict[str, Any] = {}
        self.hooks: dict[str, Any] = {}

    def register_command(self, name: str, handler: Any, **kwargs: Any) -> None:
        self.commands[name] = {"handler": handler, "kwargs": kwargs}

    def register_hook(self, name: str, handler: Any) -> None:
        self.hooks[name] = handler


def check_plugin_assets(plugin_dir: Path) -> None:
    required = [
        plugin_dir / "plugin.yaml",
        plugin_dir / "__init__.py",
        plugin_dir / "assets" / "koda" / "pet.json",
        plugin_dir / "assets" / "koda" / "spritesheet.webp",
        plugin_dir / "assets" / "koda" / "guard-peek-stop-no-panel.png",
        plugin_dir / "assets" / "koda" / "stop-sign-run-front-strip.png",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    require(not missing, "missing plugin files: " + ", ".join(missing))
    manifest = (plugin_dir / "plugin.yaml").read_text(encoding="utf-8", errors="ignore")
    for hook in ("pre_llm_call", "post_llm_call", "pre_tool_call", "post_tool_call"):
        require(f"  - {hook}" in manifest, f"plugin manifest does not advertise {hook}")


def check_plugin_runtime(plugin_dir: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="hermes-pet-plugin-home.", dir="/private/tmp") as home_name:
        plugin = load_plugin(plugin_dir, Path(home_name))
        events = patch_plugin_overlay(plugin)

        source = (plugin_dir / "__init__.py").read_text(encoding="utf-8", errors="ignore")
        local_repo_path = str(Path.home() / "Documents" / "Pet")
        require(local_repo_path not in source, "plugin source contains a local repo path")
        require('["ps", "-p"' not in source, "plugin must not poll ps while Hermes pet is awake")
        require('[sys.executable, "-c"' not in source, "plugin overlay launch must not spawn a temporary python helper")
        require("osascript" not in source, "plugin must not spawn osascript from the Hermes terminal")
        require("subprocess.check_output" not in source, "plugin must not run helper commands to position the Hermes pet")
        require(plugin.DEFAULT_SPRITESHEET_FILE.is_file(), "plugin spritesheet is missing")
        for companion_id in PACKAGED_COMPANIONS:
            require((plugin_dir / "assets" / companion_id / "pet.json").is_file(), f"{companion_id} pet.json is missing")
            require((plugin_dir / "assets" / companion_id / "spritesheet.webp").is_file(), f"{companion_id} spritesheet is missing")

        ctx = FakeHermesContext()
        plugin.register(ctx)
        require("pet" in ctx.commands, "missing /pet command registration")
        for hook in ("pre_llm_call", "post_llm_call", "pre_tool_call", "post_tool_call"):
            require(hook in ctx.hooks, f"missing hook registration: {hook}")
        for state_name in ("idle", "thinking", "working", "success", "blocked", "error", "sleeping", "reminding", "learning", "recalling"):
            require(state_name in plugin.HermesPetStateManager.supported_states, f"missing Hermes state: {state_name}")
        require(plugin.HermesPetStateManager.overlay_state("blocked") == "stop-sign", "blocked state did not map to stop-sign")
        require(plugin.HermesPetStateManager.overlay_state("recalling") == "review", "recalling state did not map to review")

        version = plugin._plugin_version()
        help_card = plugin._handle_pet("help")
        for expected in ("/pet wake", "/pet companions", "/pet companion <id>", "/pet version", "/pet update", "/pet approve <code>"):
            require(expected in help_card, f"help output missing {expected}")
        require(f"version {version}" in help_card, "help output did not show installed version")
        require("roles are themes today" in help_card, "help output did not clarify current companion roles")

        card = plugin._handle_pet("wake")
        require("awake" in card, "wake did not report awake")
        require(f"version: {version}" in card, "wake card did not show installed version")
        state = plugin._load()
        require(state["awake"] is True and state["mood"] == "idle", "wake did not persist awake idle state")
        require(state["dance_enabled"] is False, "dance mode must default to off")
        require("dance: off" in card, "wake card did not show dance mode as off")

        dance_on = plugin._handle_pet("dance on")
        if plugin._pet_supports_dance(plugin._active_pet_id()):
            require("dance: on" in dance_on, "dance on did not report enabled")
            require(plugin._load()["dance_enabled"] is True, "dance on did not persist enabled state")
        else:
            require("dance unavailable" in dance_on, "dance on did not report unavailable without dance assets")
            require(plugin._load()["dance_enabled"] is False, "dance on should stay disabled without dance assets")
        dance_off = plugin._handle_pet("dance off")
        require("dance: off" in dance_off, "dance off did not report disabled")
        require(plugin._load()["dance_enabled"] is False, "dance off did not persist disabled state")
        companions = plugin._handle_pet("companions")
        for display_name in ("Koda", "Miko", "Bramble", "Nyx", "Pip", "Atlas"):
            require(display_name in companions, f"companions roster did not render {display_name}")
        for companion_id in PACKAGED_COMPANIONS:
            require(companion_id in companions and "available" in companions, f"companions roster did not mark {companion_id} as available")
            switched = plugin._handle_pet(f"companion {companion_id}")
            require(f"pet: {companion_id}" in switched, f"companion switch did not activate {companion_id}")
            require(plugin._load()["active_pet"] == companion_id, f"companion switch did not persist {companion_id}")
        switched_back = plugin._handle_pet("companion koda")
        require("pet: koda" in switched_back, "companion switch did not return to Koda")
        version_help = plugin._handle_pet("version")
        require(version_help == f"Hermes Agent Pets version {version}", "version command did not show installed version")
        update_help = plugin._handle_pet("update")
        require(f"installed version: {version}" in update_help and "curl -fsSL" in update_help and "restart hermes agent" in update_help.lower(), "update help did not explain terminal update flow")

        plugin._on_pre_llm_call("please run tests")
        require(plugin._load()["mood"] == "thinking", "pre LLM did not set thinking")
        plugin._on_post_llm_call("done")
        require(plugin._load()["mood"] == "idle", "post LLM did not return idle")

        result = plugin._on_pre_tool_call("exec_command", {"command": "echo ok"})
        require(result is None, "safe command was unexpectedly blocked")
        require(plugin._load()["mood"] == "running", "safe command did not set running")
        plugin._on_post_tool_call("exec_command", {"command": "echo ok"}, json.dumps({"exit_code": 0}))
        require(plugin._load()["mood"] == "succeeded", "successful command did not set succeeded")

        noisy_success = 'search result mentioned "error" text and timeout docs, but command succeeded'
        for _index in range(3):
            plugin._on_post_tool_call("exec_command", {"command": "echo ok"}, noisy_success)
            current = plugin._load()
            require(current["mood"] == "succeeded", "benign output text was misclassified as a tool failure")
            require(current["failure_count"] == 0, "benign output text incremented failure count")

        plugin._on_post_tool_call("exec_command", {"command": "python"}, "Traceback (most recent call last):\nboom")
        require(plugin._load()["mood"] == "failed", "explicit traceback text was not treated as a failure")
        plugin._on_post_tool_call("exec_command", {"command": "echo ok"}, json.dumps({"exit_code": 0}))
        require(plugin._load()["failure_count"] == 0, "successful command did not reset failure count")

        for index in range(3):
            plugin._on_post_tool_call("exec_command", {"command": "false"}, json.dumps({"exit_code": 1}))
            mood = plugin._load()["mood"]
            expected = "stop-sign" if index == 2 else "failed"
            require(mood == expected, f"failure {index + 1} set {mood}, expected {expected}")

        blocked = plugin._on_pre_tool_call("exec_command", {"command": "git reset --hard"})
        require(isinstance(blocked, dict) and blocked.get("action") == "block", "dangerous command was not blocked")
        require(plugin._load()["mood"] == "stop-sign", "dangerous command did not set stop-sign")

        command = "rm /tmp/hermes-pet-audit-delete"
        plugin._overlay_confirm_delete = lambda code, deletion: "timeout"
        blocked = plugin._on_pre_tool_call("exec_command", {"command": command})
        require(isinstance(blocked, dict) and blocked.get("action") == "block", "unapproved deletion was not blocked")
        code = plugin._code_for(command)
        require(code in plugin._load().get("pending_approvals", {}), "deletion did not create a pending approval")

        approved = plugin._handle_pet(f"approve {code}")
        require("approved" in approved.lower(), "text approval did not approve deletion")
        plugin._overlay_confirm_delete = lambda code, deletion: (_ for _ in ()).throw(CheckFailure("approved deletion prompted again"))
        allowed = plugin._on_pre_tool_call("exec_command", {"command": command})
        require(allowed is None, "approved deletion retry was not allowed")

        cancel_command = "python3 -c 'import os; os.remove(\"/tmp/hermes-pet-cancelled\")'"
        plugin._overlay_confirm_delete = lambda code, deletion: "cancel"
        cancelled = plugin._on_pre_tool_call("exec_command", {"command": cancel_command})
        require(isinstance(cancelled, dict) and cancelled.get("action") == "block", "cancelled deletion was not blocked")
        require("denied_approvals" in plugin._load(), "cancelled deletion did not store denial")

        require(any(event[0] == "send" and event[1] == "stop-sign" for event in events), "stop-sign was never sent to overlay")


def check_plugin_launch_args(plugin_dir: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="hermes-pet-plugin-launch.", dir="/private/tmp") as home_name:
        plugin = load_plugin(plugin_dir, Path(home_name))
        fake_overlay = Path(home_name) / "hermes-pet-overlay"
        fake_overlay.write_text("#!/bin/sh\n", encoding="utf-8")
        plugin.OVERLAY_EXE = fake_overlay
        plugin._overlay_running = lambda: False
        plugin._start_heartbeat = lambda: None
        plugin._register_overlay_cleanup = lambda: None
        plugin._cleanup_stale_overlay_files = lambda: None
        plugin._overlay_send = lambda *args, **kwargs: None
        captured: list[list[str]] = []

        def fake_spawn(args: list[str]) -> bool:
            captured.append(args)
            return True

        plugin._spawn_detached_overlay = fake_spawn
        require(plugin._overlay_launch("idle"), "overlay launch did not return success")
        require(captured and "--anchor-front-window" in captured[-1], "overlay launch does not anchor to the front Hermes window by default")
        require("--audio-reactive" not in captured[-1], "overlay launch must not enable dancing by default")

        state = plugin._load()
        if plugin._pet_supports_dance(plugin._active_pet_id(state)):
            state["dance_enabled"] = True
            plugin._save(state)
            require(plugin._overlay_launch("idle"), "overlay launch with dance enabled did not return success")
            require("--audio-reactive" in captured[-1], "overlay launch did not enable audio-reactive dancing after /pet dance on")

            state["dance_enabled"] = False
            plugin._save(state)

        for pet_id in PACKAGED_COMPANIONS:
            state["active_pet"] = pet_id
            plugin._save(state)
            require(plugin._overlay_launch("idle"), f"overlay launch with {pet_id} did not return success")
            asset_dir = plugin.PLUGIN_DIR / "assets" / pet_id
            require(str(asset_dir / "spritesheet.webp") in captured[-1], f"overlay launch did not use {pet_id} spritesheet")
            require(
                "--stop-pose" in captured[-1]
                and captured[-1][captured[-1].index("--stop-pose") + 1] == str(asset_dir / "guard-peek-stop-no-panel.png"),
                f"overlay launch did not use {pet_id} custom stop pose",
            )
            require(
                "--panel-shell" in captured[-1]
                and captured[-1][captured[-1].index("--panel-shell") + 1] == str(asset_dir / "panel-shell.png"),
                f"overlay launch did not use {pet_id} custom control panel",
            )
            require(
                "--stop-run-pose" in captured[-1]
                and captured[-1][captured[-1].index("--stop-run-pose") + 1] == str(asset_dir / "stop-sign-run-front-strip.png"),
                f"overlay launch did not use {pet_id} front-facing stop-sign run strip",
            )
            require(
                "--pet-name" in captured[-1]
                and captured[-1][captured[-1].index("--pet-name") + 1] == pet_id.title(),
                f"overlay launch did not pass {pet_id} pet name",
            )

        state["active_pet"] = "koda"
        plugin._save(state)

        os.environ["HERMES_PET_ANCHOR_TO_FRONT_WINDOW"] = "0"
        require(plugin._overlay_launch("idle"), "overlay launch with disabled anchor did not return success")
        require("--anchor-front-window" not in captured[-1], "overlay launch ignored HERMES_PET_ANCHOR_TO_FRONT_WINDOW=0")
        os.environ.pop("HERMES_PET_ANCHOR_TO_FRONT_WINDOW", None)

        captured.clear()
        os.environ["HERMES_PET_DANCE_ON_BY_DEFAULT"] = "1"
        require(plugin._overlay_launch("idle"), "overlay launch with default dance env did not return success")
        if plugin._pet_supports_dance(plugin._active_pet_id(state)):
            require("--audio-reactive" in captured[-1], "dance-capable pet did not honor default dance env")
        else:
            require("--audio-reactive" not in captured[-1], "default dance env enabled audio mode without dance assets")
        os.environ.pop("HERMES_PET_DANCE_ON_BY_DEFAULT", None)


def load_hook(temp_root: Path) -> ModuleType:
    root = repo_root()
    os.environ["HERMES_PET_AWAKE_FILE"] = str(temp_root / "awake")
    os.environ["HERMES_PET_HERMES_ACTIVE_DIR"] = str(temp_root / "active")
    os.environ["HERMES_PET_HERMES_FAILURE_FILE"] = str(temp_root / "failures")
    os.environ["HERMES_PET_HERMES_CONFIRM_DIR"] = str(temp_root / "confirm")
    os.environ["HERMES_PET_HERMES_CONFIRM_SECONDS"] = "0.01"
    os.environ.pop("HERMES_PET_CTL", None)
    return import_module(root / "scripts" / "hermes-pet-hook.py", f"hermes_pet_hook_test_{time.time_ns()}")


def check_legacy_hook_runtime() -> None:
    with tempfile.TemporaryDirectory(prefix="hermes-pet-hook.", dir="/private/tmp") as temp_name:
        temp_root = Path(temp_name)
        hook = load_hook(temp_root)
        states: list[str] = []
        watched: list[Path] = []
        hook.AWAKE_FILE.touch()
        hook.pet = lambda state: states.append(state)
        hook.start_watcher = lambda path: watched.append(path)

        require(hook.HERMES_PET_CTL == repo_root() / "scripts" / "hermes-pet", "legacy hook default control path is not repo-relative")

        payload = {
            "session_id": "session-a",
            "tool_name": "exec_command",
            "tool_input": {"command": "echo stable"},
        }
        first = hook.safe_id(payload)
        time.sleep(0.01)
        second = hook.safe_id(payload)
        require(first == second, "safe_id fallback is not stable")

        hook.handle_pre(payload)
        active = hook.active_path(first)
        require(active.exists(), "pre hook did not create active watcher file")
        require(states[-1] == "running", "pre hook did not set running")

        post_payload = dict(payload)
        post_payload["extra"] = {"result": json.dumps({"exit_code": 0})}
        hook.handle_post(post_payload)
        require(not active.exists(), "post hook did not remove matching active watcher file")
        require(states[-1] == "success", "post hook did not set success")

        require(not hook.is_failed_result('search result mentioned "error" and timeout docs'), "legacy hook misclassified benign output as failure")
        require(hook.is_failed_result("Traceback (most recent call last):\nboom"), "legacy hook missed traceback failure")
        require(hook.needs_delete_confirmation("rm README.md"), "rm command was not recognized as deletion-like")
        require(hook.needs_delete_confirmation("python3 -c 'import os; os.remove(\"/tmp/x\")'"), "Python deletion was not recognized")
        require(hook.is_dangerous("git push --force"), "dangerous git command was not recognized")


def check_installer_safety(root: Path) -> None:
    installer = root / "scripts" / "install-hermes-agent-pet.sh"
    with tempfile.TemporaryDirectory(prefix="hermes-pet-install-safety.", dir="/private/tmp") as temp_name:
        env = dict(os.environ)
        env["HERMES_PLUGIN_DIR"] = str(Path(temp_name) / "plugins")
        for unsafe_name in ("../bad", ".", "-rf"):
            result = subprocess.run(
                [str(installer), unsafe_name],
                cwd=str(root),
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            require(result.returncode == 2, f"installer accepted unsafe plugin name: {unsafe_name}")
            require("unsafe plugin name" in result.stderr, "installer did not explain unsafe plugin name rejection")


def check_overlay_binary(root: Path, plugin_dir: Path, audio_reactive: bool) -> None:
    installed_overlay = plugin_dir / "bin" / "hermes-pet-overlay"
    overlay = installed_overlay if installed_overlay.is_file() else root / "build" / "HermesPetOverlay.app" / "Contents" / "MacOS" / "hermes-pet-overlay"
    require(overlay.is_file() and os.access(overlay, os.X_OK), f"overlay executable is missing: {overlay}")

    def run_overlay_smoke(pet_id: str) -> None:
        asset_dir = plugin_dir / "assets" / pet_id
        spritesheet = asset_dir / "spritesheet.webp"
        require(spritesheet.is_file(), f"{pet_id} spritesheet is missing: {spritesheet}")
        with tempfile.TemporaryDirectory(prefix="hermes-pet-overlay.", dir="/private/tmp") as temp_name:
            temp_root = Path(temp_name)
            state_file = temp_root / "state"
            awake_file = temp_root / "awake"
            position_file = temp_root / "position"
            heartbeat_file = temp_root / "heartbeat"
            decision_file = temp_root / "delete.decision"
            awake_file.touch()
            heartbeat_file.write_text(f"{time.time():.6f}\n")
            args = [
                str(overlay),
                "--main-screen-only",
                "--state", "idle",
                "--state-file", str(state_file),
                "--awake-file", str(awake_file),
                "--position-file", str(position_file),
                "--heartbeat-file", str(heartbeat_file),
                "--heartbeat-timeout", "3.0",
                "--spritesheet", str(spritesheet),
                "--no-activity-monitor",
                "--clickable",
                "--scale", "0.30",
                "--margin", "24",
                "--pet-name", pet_id.title(),
                "--stop-pose", str(asset_dir / "guard-peek-stop-no-panel.png"),
                "--stop-run-pose", str(asset_dir / "stop-sign-run-front-strip.png"),
                "--panel-shell", str(asset_dir / "panel-shell.png"),
            ]
            if audio_reactive:
                args.append("--audio-reactive")
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                time.sleep(1.0)
                require(process.poll() is None, f"overlay exited immediately for {spritesheet}")
                state_file.write_text(f"running {time.time():.6f} test running\n")
                time.sleep(0.3)
                require(process.poll() is None, f"overlay exited after running state for {spritesheet}")
                state_file.write_text(f"stop-sign {time.time():.6f} test stop\n")
                time.sleep(0.3)
                require(process.poll() is None, f"overlay exited after stop-sign state for {spritesheet}")
                state_file.write_text(f"confirm-delete {decision_file} test delete\n")
                time.sleep(0.4)
                require(process.poll() is None, f"overlay exited after confirm-delete state for {spritesheet}")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    process.kill()
            stdout = process.stdout.read() if process.stdout else ""
            stderr = process.stderr.read() if process.stderr else ""
            if process.returncode not in (0, -15):
                raise CheckFailure(f"overlay exited with {process.returncode}: {stdout} {stderr}")

    for pet_id in PACKAGED_COMPANIONS:
        run_overlay_smoke(pet_id)


def main() -> int:
    root = repo_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin", default=root / "hermes-agent-pets" / "hermes-pet-agent", type=Path, help="Plugin package directory to test.")
    parser.add_argument("--overlay", action="store_true", help="Launch the native overlay briefly and test state-file updates.")
    parser.add_argument("--audio-reactive", action="store_true", help="Include --audio-reactive in the overlay smoke test.")
    args = parser.parse_args()

    plugin_dir = args.plugin.expanduser().resolve()
    try:
        check_plugin_assets(plugin_dir)
        line("ok", "plugin assets", str(plugin_dir))
        check_plugin_runtime(plugin_dir)
        line("ok", "plugin runtime hooks", str(plugin_dir))
        check_plugin_launch_args(plugin_dir)
        line("ok", "plugin launch args", str(plugin_dir))
        check_legacy_hook_runtime()
        line("ok", "legacy shell hook runtime")
        check_installer_safety(root)
        line("ok", "installer safety")
        if args.overlay:
            check_overlay_binary(root, plugin_dir, args.audio_reactive)
            label = "native overlay smoke"
            if args.audio_reactive:
                label += " with audio-reactive flag"
            line("ok", label)
    except CheckFailure as exc:
        line("fail", "runtime regression", str(exc))
        return 1
    print("Hermes pet runtime checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
