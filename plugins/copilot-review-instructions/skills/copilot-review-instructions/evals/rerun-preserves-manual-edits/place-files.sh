#!/usr/bin/env bash
# Builds the same fixture as fresh-dbt-python-repo, then adds instruction files from an earlier run
# plus a later manual edit by a teammate, so a re-run must merge instead of overwrite.
set -eu
here="$(cd "$(dirname "$0")" && pwd)"
bash "$here/../fresh-dbt-python-repo/place-files.sh"
cd repo
mkdir -p .github/instructions
# Earlier skill run: everything except Priya's line.
grep -v "Priya" "$here/files/repo/.github/copilot-instructions.md" > .github/copilot-instructions.md
cp "$here/files/repo/.github/instructions/dbt.instructions.md" .github/instructions/
git add .github && git commit -q -m "chore(copilot-review): add repo review instructions"
# Manual edit by a teammate afterwards.
cp "$here/files/repo/.github/copilot-instructions.md" .github/copilot-instructions.md
git -c user.name=Priya -c user.email=priya@example.com commit -q -am "Add select * rule after Power BI incident"
