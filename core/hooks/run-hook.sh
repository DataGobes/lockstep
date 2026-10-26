#!/usr/bin/env bash
# Lockstep hook shim for Claude Code and GitHub Copilot.
#   usage: run-hook.sh <protect_tests|guard_bash>   (event JSON on stdin)
# Runs the Python hook from ../src next to this script. Exit 0 allows, exit 2 blocks.
# Fails closed: if Python 3.11+ is missing, the tool call is blocked.
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hook="${1:-}"
case "$hook" in
  protect_tests|guard_bash) ;;
  *) echo "lockstep: unknown hook '$hook'" >&2; exit 2 ;;
esac
# The first Python 3.11+ found: $LOCKSTEP_PYTHON, then versioned names, then python3 and python.
# Versioned names come first because python3 on PATH is often an older system Python (macOS ships 3.9),
# and hooks don't see the interpreter selected in the editor.
# Editors started from the Dock get a minimal PATH, so also look where Python installers put it.
PATH="$PATH:/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:${HOME:-}/.local/bin"
py=""
for cand in ${LOCKSTEP_PYTHON:-} python3.14 python3.13 python3.12 python3.11 python3 python; do
  p="$(command -v "$cand" 2>/dev/null)" || continue
  if "$p" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    py="$p"
    break
  fi
done
if [ -z "$py" ]; then
  echo "lockstep: Python 3.11+ is required for the Lockstep hooks and was not found on PATH; blocking to be safe." \
    "Install one, or set LOCKSTEP_PYTHON to its path." >&2
  exit 2
fi
# -s: ignore user site-packages. The package path is passed as an argument, not via PYTHONPATH.
exec "$py" -s -c '
import sys
sys.path.insert(0, sys.argv[1])
import importlib
importlib.import_module("lockstep_checks.hooks." + sys.argv[2]).main()
' "$here/../src" "$hook"
