#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
plugin_name="${1:-hermes-pet-agent}"
plugin_src="$repo_root/hermes-agent-pets/$plugin_name"
dest_root="${HERMES_PLUGIN_DIR:-$HOME/.hermes/plugins}"
plugin_dest="$dest_root/$plugin_name"

usage() {
  cat <<'USAGE'
Usage: scripts/install-hermes-agent-pet.sh [plugin-name]

Installs an agent pet plugin into ~/.hermes/plugins by default.
Set HERMES_PLUGIN_DIR to rehearse or install somewhere else.
USAGE
}

enable_live_plugin_config() {
  local config_file="$HOME/.hermes/config.yaml"

  if [[ "${HERMES_PLUGIN_DIR:-}" != "" ]]; then
    return 0
  fi

  mkdir -p "$(dirname "$config_file")"
  if [[ ! -f "$config_file" ]]; then
    {
      echo "plugins:"
      echo "  enabled:"
      echo "  - $plugin_name"
    } >"$config_file"
    return 0
  fi

  if grep -Eq "^[[:space:]]*-[[:space:]]*$plugin_name[[:space:]]*$" "$config_file"; then
    return 0
  fi

  python3 - "$config_file" "$plugin_name" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

config = Path(sys.argv[1])
plugin = sys.argv[2]
lines = config.read_text(encoding="utf-8").splitlines()

plugins_index = next((i for i, line in enumerate(lines) if line == "plugins:"), None)
if plugins_index is None:
    lines.extend(["plugins:", "  enabled:", f"  - {plugin}"])
else:
    next_top = next((i for i in range(plugins_index + 1, len(lines)) if lines[i] and not lines[i].startswith((" ", "\t", "#"))), len(lines))
    enabled_index = next((i for i in range(plugins_index + 1, next_top) if lines[i].strip() == "enabled:"), None)
    if enabled_index is None:
        lines[plugins_index + 1:plugins_index + 1] = ["  enabled:", f"  - {plugin}"]
    else:
        insert_at = enabled_index + 1
        while insert_at < next_top and (lines[insert_at].startswith("  - ") or not lines[insert_at].strip()):
            insert_at += 1
        lines.insert(insert_at, f"  - {plugin}")

config.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ ! "$plugin_name" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]]; then
  echo "unsafe plugin name: $plugin_name" >&2
  echo "plugin names must start with a letter or number and may only contain letters, numbers, '.', '_' and '-'" >&2
  exit 2
fi

if [[ ! -d "$plugin_src" ]]; then
  echo "missing plugin package: $plugin_src" >&2
  exit 1
fi

if [[ ! -f "$plugin_src/plugin.yaml" || ! -f "$plugin_src/__init__.py" ]]; then
  echo "plugin package is incomplete: $plugin_src" >&2
  exit 1
fi

case "$plugin_name" in
  hermes-pet-agent)
    for pet_id in koda miko bramble nyx pip atlas; do
      "$repo_root/scripts/package-hermes-pet.py" \
        --character "$repo_root/character-sets/$pet_id" \
        --plugin "$plugin_src" \
        --asset-id "$pet_id" >/dev/null
    done
    "$repo_root/scripts/hermes-pet-overlay/build.sh" >/dev/null
    ;;
  *)
    echo "no automatic build recipe for plugin: $plugin_name" >&2
    echo "installing existing package contents only" >&2
    ;;
esac

mkdir -p "$dest_root"
dest_root_real="$(cd "$dest_root" && pwd -P)"
plugin_dest="$dest_root_real/$plugin_name"
case "$plugin_dest" in
  "$dest_root_real"/*) ;;
  *)
    echo "refusing to install outside plugin directory: $plugin_dest" >&2
    exit 2
    ;;
esac

rm -rf "$plugin_dest"
mkdir -p "$plugin_dest"
cp -R "$plugin_src"/. "$plugin_dest"/
if [[ -f "$repo_root/hermes-agent-pets/companions.json" ]]; then
  cp "$repo_root/hermes-agent-pets/companions.json" "$dest_root/companions.json"
  rm -f "$plugin_dest/companions.json"
fi

if [[ "$plugin_name" == "hermes-pet-agent" ]]; then
  overlay="$repo_root/build/HermesPetOverlay.app/Contents/MacOS/hermes-pet-overlay"
  if [[ ! -x "$overlay" ]]; then
    echo "missing built overlay executable: $overlay" >&2
    exit 1
  fi
  mkdir -p "$plugin_dest/bin"
  cp "$overlay" "$plugin_dest/bin/hermes-pet-overlay"
  chmod +x "$plugin_dest/bin/hermes-pet-overlay"
fi

find "$plugin_dest" \
  \( -name '.DS_Store' -o -name '__pycache__' -o -name '*.pyc' \) \
  -exec rm -rf {} +
enable_live_plugin_config
echo "installed $plugin_name"
echo "$plugin_dest"
echo "restart Hermes, then run /pet help"
