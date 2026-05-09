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
echo "installed $plugin_name"
echo "$plugin_dest"
echo "restart Hermes, then run /pet wake"
