#!/usr/bin/env python3
"""Patch the local Hermes TUI to hide its terminal spinner while Hermes pet is awake."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


HELPER = '''\
    # HERMES PET SPINNER PATCH START
    def _hermes_pet_hides_terminal_spinner(self) -> bool:
        """Hide Hermes' in-terminal spinner while the native Hermes pet is awake."""
        try:
            raw = str(os.environ.get("HERMES_PET_SHOW_TERMINAL_SPINNER", "")).strip().lower()
            if raw in {"1", "true", "yes", "on"}:
                return False
            state_file = Path.home() / ".hermes" / "hermes-pet-agent" / "state.json"
            data = json.loads(state_file.read_text(encoding="utf-8"))
            return isinstance(data, dict) and bool(data.get("awake"))
        except Exception:
            return False
    # HERMES PET SPINNER PATCH END

'''


def default_cli_path() -> Path:
    return Path.home() / ".hermes" / "hermes-agent" / "cli.py"


def patch_text(source: str) -> tuple[str, bool]:
    changed = False
    if "HERMES PET SPINNER PATCH START" not in source:
        anchor = (
            "    def _tui_input_rule_height(self, position: str, width: Optional[int] = None) -> int:\n"
        )
        if anchor not in source:
            raise RuntimeError("could not find TUI input rule anchor")
        source = source.replace(anchor, HELPER + anchor, 1)
        changed = True

    replacements = {
        '    def _agent_spacer_height(self, width: Optional[int] = None) -> int:\n'
        '        """Return the spacer height shown above the status bar while the agent runs."""\n'
        '        if not getattr(self, "_agent_running", False):\n':
        '    def _agent_spacer_height(self, width: Optional[int] = None) -> int:\n'
        '        """Return the spacer height shown above the status bar while the agent runs."""\n'
        '        if self._hermes_pet_hides_terminal_spinner():\n'
        '            return 0\n'
        '        if not getattr(self, "_agent_running", False):\n',

        '    def _spinner_widget_height(self, width: Optional[int] = None) -> int:\n'
        '        """Return the visible height for the spinner/status text line above the status bar."""\n'
        '        spinner_line = self._render_spinner_text()\n':
        '    def _spinner_widget_height(self, width: Optional[int] = None) -> int:\n'
        '        """Return the visible height for the spinner/status text line above the status bar."""\n'
        '        if self._hermes_pet_hides_terminal_spinner():\n'
        '            return 0\n'
        '        spinner_line = self._render_spinner_text()\n',

        '    def _render_spinner_text(self) -> str:\n'
        '        """Return the live spinner/status text exactly as rendered in the TUI."""\n'
        '        txt = getattr(self, "_spinner_text", "")\n':
        '    def _render_spinner_text(self) -> str:\n'
        '        """Return the live spinner/status text exactly as rendered in the TUI."""\n'
        '        if self._hermes_pet_hides_terminal_spinner():\n'
        '            return ""\n'
        '        txt = getattr(self, "_spinner_text", "")\n',
    }
    for old, new in replacements.items():
        if new in source:
            continue
        if old not in source:
            raise RuntimeError("could not find expected spinner patch target")
        source = source.replace(old, new, 1)
        changed = True
    return source, changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, default=default_cli_path(), help="Path to Hermes cli.py.")
    parser.add_argument("--check", action="store_true", help="Check whether the patch is present without writing.")
    args = parser.parse_args()

    cli_path = args.cli.expanduser().resolve()
    source = cli_path.read_text(encoding="utf-8")
    patched, changed = patch_text(source)
    if args.check:
        print("patched" if not changed else "needs patch")
        return 1 if changed else 0
    if not changed:
        print(f"already patched: {cli_path}")
        return 0
    backup = cli_path.with_suffix(cli_path.suffix + ".bak.hermes-pet-spinner")
    if not backup.exists():
        shutil.copy2(cli_path, backup)
    cli_path.write_text(patched, encoding="utf-8")
    print(f"patched: {cli_path}")
    print(f"backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
