# Source this from zsh to let the Hermes pet react to terminal commands.
#
#   source /path/to/Pet/scripts/hermes-pet-shell.zsh

_hermes_pet_shell_file="${(%):-%N}"
_hermes_pet_shell_dir="${_hermes_pet_shell_file:A:h}"

export HERMES_PET_CTL="${HERMES_PET_CTL:-$_hermes_pet_shell_dir/hermes-pet}"
export HERMES_PET_CLI="${HERMES_PET_CLI:-$_hermes_pet_shell_dir/pet}"
export HERMES_PET_AWAKE_FILE="${HERMES_PET_AWAKE_FILE:-/tmp/hermes-pet-overlay-awake}"
export HERMES_PET_FAILURE_FILE="${HERMES_PET_FAILURE_FILE:-/tmp/hermes-pet-terminal-failures}"

pet() {
  "$HERMES_PET_CLI" "$@"
}

hermes_pet_preexec() {
  local command="$1"
  [[ -f "$HERMES_PET_AWAKE_FILE" ]] || return 0
  if hermes_pet_is_dangerous_command "$command"; then
    "$HERMES_PET_CTL" stop-sign >/dev/null 2>&1 || true
    return 0
  fi
  "$HERMES_PET_CTL" running >/dev/null 2>&1 || true
}

hermes_pet_precmd() {
  local exit_status=$?
  [[ -f "$HERMES_PET_AWAKE_FILE" ]] || return 0
  if [[ "$exit_status" -eq 0 ]]; then
    print -r -- 0 > "$HERMES_PET_FAILURE_FILE"
    "$HERMES_PET_CTL" idle >/dev/null 2>&1 || true
  else
    local failures=0
    [[ -f "$HERMES_PET_FAILURE_FILE" ]] && failures="$(<"$HERMES_PET_FAILURE_FILE")"
    [[ "$failures" == <-> ]] || failures=0
    failures=$((failures + 1))
    print -r -- "$failures" > "$HERMES_PET_FAILURE_FILE"
    if (( failures >= 3 )); then
      "$HERMES_PET_CTL" stop-sign >/dev/null 2>&1 || true
    else
      "$HERMES_PET_CTL" failed >/dev/null 2>&1 || true
    fi
  fi
}

hermes_pet_is_dangerous_command() {
  local command="$1"
  local normalized="${command:l}"

  [[ "$normalized" == *"rm -rf /"* ]] && return 0
  [[ "$normalized" == *"rm -rf ~"* ]] && return 0
  [[ "$normalized" == *"rm -rf ."* ]] && return 0
  [[ "$normalized" == *"sudo rm -rf"* ]] && return 0
  [[ "$normalized" == *"git push --force"* ]] && return 0
  [[ "$normalized" == *"git push -f"* ]] && return 0
  [[ "$normalized" == *"git reset --hard"* ]] && return 0
  [[ "$normalized" == *"chmod -r 777"* ]] && return 0
  [[ "$normalized" == *":(){ :|:& };:"* ]] && return 0

  return 1
}

autoload -Uz add-zsh-hook
add-zsh-hook preexec hermes_pet_preexec
add-zsh-hook precmd hermes_pet_precmd
