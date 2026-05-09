#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
line="source $root/scripts/hermes-pet-shell.zsh"
zshrc="${ZDOTDIR:-$HOME}/.zshrc"

touch "$zshrc"

if grep -Fqx "$line" "$zshrc"; then
  echo "Hermes pet zsh hook already installed in $zshrc"
  exit 0
fi

{
  echo ""
  echo "# Hermes pet terminal reactions"
  echo "$line"
} >> "$zshrc"

echo "Installed Hermes pet zsh hook in $zshrc"
