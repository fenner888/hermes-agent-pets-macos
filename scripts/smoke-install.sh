#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_root="$(mktemp -d "${TMPDIR:-/tmp}/hermes-pet-smoke.XXXXXX")"
plugin_root="$tmp_root/plugins"
run_overlay=0
keep=0

usage() {
  cat <<'USAGE'
Usage: scripts/smoke-install.sh [--overlay] [--keep]

Runs a clean install rehearsal into a temporary Hermes plugin directory.

Options:
  --overlay  Also launch the native macOS overlay smoke test.
  --keep     Keep the temporary directory for inspection.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --overlay)
      run_overlay=1
      ;;
    --keep)
      keep=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

cleanup() {
  if [[ "$keep" -eq 0 ]]; then
    rm -rf "$tmp_root"
  else
    echo "kept smoke directory: $tmp_root"
  fi
}
trap cleanup EXIT

mkdir -p "$plugin_root"

cd "$repo_root"

scripts/validate-hermes-companions.py
for pet_id in koda miko bramble nyx pip atlas; do
  scripts/validate-hermes-pet.py "character-sets/$pet_id" >/dev/null
done

scripts/hermes-pet-overlay/build.sh >/dev/null
HERMES_PLUGIN_DIR="$plugin_root" scripts/install-hermes-agent-pet.sh >/dev/null
scripts/test-hermes-agent-pet.py --plugin "$plugin_root/hermes-pet-agent"

if [[ "$run_overlay" -eq 1 ]]; then
  scripts/test-hermes-agent-pet.py --plugin "$plugin_root/hermes-pet-agent" --overlay
fi

echo "smoke install passed: $plugin_root/hermes-pet-agent"
