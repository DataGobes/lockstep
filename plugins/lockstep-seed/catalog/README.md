# Practice catalogue

One TOML file per practice. The engine (`scripts/compose.py`) reads every `*.toml` here, then the org folder
(`--catalog`), then `.workflow/practices/` in the repo; a later layer replaces a practice with the same `id`.

| Field | Meaning |
|---|---|
| `id`, `title` | Stable id (kebab-case) and a one-line name. |
| `prevents` | The failure this practice prevents, in the words a team would use. |
| `kind` | `mechanical` (hook, check, setting) or `instruction` (a line the agent reads). |
| `cost` | `low`, `medium` or `high`: setup plus daily friction. |
| `start` | `risk` (added at seeding when its signals match: irreversible harm), `context` (added at seeding when its signals match: something the agent cannot find out), or `evidence` (only when the team names a failure). |
| `signals` | Probe signals that make it relevant; any one is enough. Empty means always relevant. |
| `answers` | Interview answers (true/false) that also make it apply, e.g. `pii`. |
| `failures` | Short phrases describing the failures it prevents, for the grow skill to match against. |
| `review_after_days` | When the grow skill should ask whether it still earns its place. |
| `[render]` | What it writes: `agents_md` lines, `deny` / `ask` permission rules, `recommend` (skills to install), and `create` (starter files, written only if missing). Lines may use `{test}`, `{lint}`, `{build}` from the probe's commands; a line whose command is unknown is dropped. |
