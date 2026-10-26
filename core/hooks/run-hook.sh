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
py="$(command -v python3 || command -v python || true)"
if [ -z "$py" ]; then
  echo "lockstep: Python 3.11+ is required for the Lockstep hooks and was not found; blocking to be safe." >&2
  exit 2
fi
# -s: ignore user site-packages. The package path is passed as an argument, not via PYTHONPATH.
exec "$py" -s -c '
import sys
if sys.version_info < (3, 11):
    print("lockstep: Python 3.11+ is required for the Lockstep hooks; blocking to be safe.", file=sys.stderr)
    sys.exit(2)
sys.path.insert(0, sys.argv[1])
import importlib
importlib.import_module("lockstep_checks.hooks." + sys.argv[2]).main()
' "$here/../src" "$hook"
