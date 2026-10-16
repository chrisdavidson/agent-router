# Sourced by bin/hook, bin/trace and bin/mcp (not a hook itself): where the router lives.
# The one place that order is decided; `agent-router doctor` replicates it in Python
# (src/agent_router/doctor.py) and a test holds the two equal. Nothing here starts Python.
#
#   ar_resolve_bin       sets AR_BIN (the agent-router executable) and AR_BRANCH, or returns 1
#                        with AR_ERR saying why
#   ar_resolve_python    sets AR_PY (an interpreter that can run trace.py) and AR_PY_BRANCH,
#                        or returns 1
#
# Order, first match wins:
#   1. env       AGENT_ROUTER_BIN / AGENT_ROUTER_PYTHON. An explicit override is final: if it
#                names something unusable we do not fall through to a different binary.
#   2. checkout  <repo>/.venv/bin/{agent-router,python}, the checkout this plugin dir sits in.
#   3. path      `agent-router` on PATH (a `uv tool install` of the fork); the interpreter is the
#                one on that script's shebang line when it is an absolute, executable python,
#                else `python3` on PATH.
# The checkout beats PATH on purpose: the plugin directory always lives in a checkout, so a stale
# PATH install must not silently outrank the code sitting next to the hooks.
#
# Run directly (`bash _resolve.sh`) it prints `bin <branch> <path>` and `python <branch> <path>`.

_ar_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# bin -> plugin -> integrations/<name> -> integrations -> repo
_ar_repo="$(dirname "$(dirname "$(dirname "$(dirname "$_ar_here")")")")"

_ar_exe() { [ -f "$1" ] && [ -x "$1" ]; }

ar_resolve_bin() {
  AR_BIN="" AR_BRANCH="" AR_ERR=""
  local c
  if [ -n "${AGENT_ROUTER_BIN:-}" ]; then
    if _ar_exe "$AGENT_ROUTER_BIN"; then AR_BIN="$AGENT_ROUTER_BIN" AR_BRANCH=env; return 0; fi
    AR_ERR="AGENT_ROUTER_BIN=$AGENT_ROUTER_BIN is not an executable file"
    return 1
  fi
  c="$_ar_repo/.venv/bin/agent-router"
  if _ar_exe "$c"; then AR_BIN="$c" AR_BRANCH=checkout; return 0; fi
  c="$(command -v agent-router 2>/dev/null)"
  if [ -n "$c" ] && _ar_exe "$c"; then AR_BIN="$c" AR_BRANCH=path; return 0; fi
  AR_ERR="agent-router not found: set AGENT_ROUTER_BIN, run 'make install' in $_ar_repo, or 'uv tool install' the fork"
  return 1
}

_ar_shebang_python() { # $1 an executable script: print its interpreter if usable, else fail
  # Two forms: `#!/abs/path/python`, and the `#!/bin/sh` + `'''exec' '/abs/python' "$0" "$@"`
  # pair that uv writes when the interpreter path is too long for a shebang.
  local line second interp re
  { IFS= read -r line; IFS= read -r second; } <"$1" 2>/dev/null || true
  case $line in '#!'*) ;; *) return 1 ;; esac
  line="${line#\#!}"
  line="${line#"${line%%[![:space:]]*}"}"
  interp="${line%%[[:space:]]*}"
  case $interp in /*) ;; *) return 1 ;; esac
  case "${interp##*/}" in
    python*) ;;
    sh | bash | dash)
      re="^'''exec'[[:space:]]+['\"]([^'\"]+)['\"]"
      [[ $second =~ $re ]] || return 1
      interp="${BASH_REMATCH[1]}"
      case $interp in /*) ;; *) return 1 ;; esac
      case "${interp##*/}" in python*) ;; *) return 1 ;; esac
      ;;
    *) return 1 ;;
  esac
  _ar_exe "$interp" || return 1
  printf '%s' "$interp"
}

ar_resolve_python() {
  AR_PY="" AR_PY_BRANCH=""
  local c
  if [ -n "${AGENT_ROUTER_PYTHON:-}" ]; then
    if _ar_exe "$AGENT_ROUTER_PYTHON"; then
      AR_PY="$AGENT_ROUTER_PYTHON" AR_PY_BRANCH=env
      return 0
    fi
    return 1
  fi
  c="$_ar_repo/.venv/bin/python"
  if _ar_exe "$c"; then AR_PY="$c" AR_PY_BRANCH=checkout; return 0; fi
  c="$(command -v agent-router 2>/dev/null)"
  if [ -n "$c" ] && _ar_exe "$c"; then
    c="$(_ar_shebang_python "$c")" && { AR_PY="$c" AR_PY_BRANCH=path; return 0; }
  fi
  c="$(command -v python3 2>/dev/null)"
  if [ -n "$c" ] && _ar_exe "$c"; then AR_PY="$c" AR_PY_BRANCH=system; return 0; fi
  return 1
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  if ar_resolve_bin; then printf 'bin %s %s\n' "$AR_BRANCH" "$AR_BIN"; else printf 'bin none %s\n' "$AR_ERR"; fi
  if ar_resolve_python; then printf 'python %s %s\n' "$AR_PY_BRANCH" "$AR_PY"; else echo 'python none'; fi
fi
