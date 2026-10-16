# Sourced by bin/hook and bin/trace (not a hook itself). The shell boundary of the fail-open
# rule: whatever the Python side does (exit non-zero, hang, print nothing, print garbage, fail to
# import), the host sees exactly one JSON object and exit 0. Fast paths never reach this file's
# Python: a clean `{}` is accepted by string comparison, and Python (one `json.loads`) runs only
# to vet a non-trivial answer such as a routing hint.
#
#   payload=...                      the hook JSON, already read from stdin
#   FAILOPEN_PY=...                  interpreter used to vet a non-trivial answer (optional)
#   FAILOPEN_EMPTY_ONLY=1            record-only caller: anything but a clean {} becomes {}
#   fail_open_run CMD [ARG...]       run CMD with $payload on stdin; print one JSON object or {}
#
# AGENT_ROUTER_HOOK_TIMEOUT (seconds, default 12) bounds the child when `timeout` exists; it sits
# below the 15 s / 10 s limits in hooks/hooks.json so a hung router yields {} rather than a host
# kill. The child's stderr passes through.

_fo_limit() {
  local v="${AGENT_ROUTER_HOOK_TIMEOUT:-12}"
  [[ $v =~ ^[0-9]+([.][0-9]+)?$ ]] && printf '%s' "$v" || printf '12'
}

_fo_is_object() { # $1 looks like {...}: confirm it parses as a JSON object, if we can
  local py="${FAILOPEN_PY:-}" rc
  { [ -n "$py" ] && [ -x "$py" ]; } || py="$(command -v python3 2>/dev/null)"
  [ -n "$py" ] || return 0   # nothing to vet with: the {...} shape check stands
  printf '%s' "$1" | "$py" -c \
    'import json,sys; sys.exit(0 if isinstance(json.loads(sys.stdin.read()), dict) else 1)' \
    >/dev/null 2>&1
  rc=$?
  [ "$rc" -eq 0 ] && return 0
  [ "$rc" -eq 1 ] && return 1
  return 0                   # the vetting interpreter itself failed to run
}

fail_open_run() {
  local out rc
  local -a guard=()
  if command -v timeout >/dev/null 2>&1; then guard=(timeout -k 1 "$(_fo_limit)"); fi
  out="$(printf '%s' "$payload" | "${guard[@]}" "$@")"
  rc=$?
  if [ "$rc" -ne 0 ]; then echo '{}'; return 0; fi
  out="${out#"${out%%[![:space:]]*}"}"
  out="${out%"${out##*[![:space:]]}"}"
  if [ "$out" = '{}' ]; then echo '{}'; return 0; fi
  if [ -n "${FAILOPEN_EMPTY_ONLY:-}" ]; then echo '{}'; return 0; fi
  if [[ $out == \{*\} ]] && [[ $out != *$'\n'* ]] && _fo_is_object "$out"; then
    printf '%s\n' "$out"
  else
    echo '{}'
  fi
  return 0
}
