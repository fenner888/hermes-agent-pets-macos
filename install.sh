#!/usr/bin/env bash
set -euo pipefail

repo="fenner888/hermes-agent-pets-macos"
ref="${HERMES_AGENT_PETS_REF:-main}"
tarball_url="${HERMES_AGENT_PETS_TARBALL_URL:-https://github.com/$repo/archive/refs/heads/$ref.tar.gz}"
tmp_root="$(mktemp -d "${TMPDIR:-/tmp}/hermes-agent-pets-install.XXXXXX")"

cleanup() {
  rm -rf "$tmp_root"
}
trap cleanup EXIT

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

need curl
need tar
need python3

archive="$tmp_root/hermes-agent-pets.tar.gz"
echo "Downloading Hermes Agent Pets for macOS..."
curl -fsSL "$tarball_url" -o "$archive"

tar -xzf "$archive" -C "$tmp_root"
repo_dir="$(find "$tmp_root" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [[ -z "$repo_dir" || ! -x "$repo_dir/scripts/install-hermes-agent-pet.sh" ]]; then
  echo "downloaded archive did not contain the Hermes Agent Pets installer" >&2
  exit 1
fi

cd "$repo_dir"
scripts/install-hermes-agent-pet.sh
installed_version="$(python3 - <<'PY'
from pathlib import Path
path = Path("hermes-agent-pets/hermes-pet-agent/plugin.yaml")
version = "unknown"
for line in path.read_text(encoding="utf-8").splitlines():
    key, _, value = line.partition(":")
    if key.strip() == "version":
        version = value.strip().strip("'\"") or "unknown"
        break
print(version)
PY
)"

cat <<EOF

Hermes Agent Pets ${installed_version} installed.

Next:
1. Restart Hermes Agent.
2. Run /pet help.
3. Run /pet wake.
4. Run /pet companions.

To update later, rerun this same install command and restart Hermes Agent.
EOF
