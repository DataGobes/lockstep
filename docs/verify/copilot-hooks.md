# Verify first: do Copilot's hooks behave like Claude's?

Desk research on 2026-10-23 against the official docs. This settles the design of the hooks; a hands-on test in
VS Code and Copilot CLI is still needed before we rely on them (see the end).

Sources:
- [Copilot CLI hooks reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-hooks-reference)
- [Agent hooks in VS Code (Preview)](https://code.visualstudio.com/docs/agent-customization/hooks)

## Findings

| Question | Answer | Effect on our design |
|---|---|---|
| Does Copilot read our hook config? | Yes. Copilot CLI and the VS Code Copilot harness both read the repo's `.claude/settings.json` and `.claude/settings.local.json`, next to `.github/hooks/*.json` and plugin `hooks.json`. | One registration in `.claude/settings.json` serves Claude and Copilot. No second hook file. |
| Same event and payload? | Under the PascalCase `PreToolUse` event, Copilot sends Claude-style `tool_name` / `tool_input` and reports Claude tool names (`Bash`, `Edit`, `Write`, `Read`). Matchers like `Edit\|Write` work. | Hooks keep parsing the Claude payload. |
| Same tool arguments? | **No guarantee.** Copilot maps several native tools onto one Claude name: `edit`, `str_replace_editor` and `apply_patch` all become `Edit`; `bash` and `powershell` become `Bash`. VS Code warns arguments may differ. | protect-tests must read the target path from several shapes, including paths inside an `apply_patch` patch. guard-bash must handle PowerShell syntax too. |
| How does a hook block? | Claude: exit code 2. Copilot: `preToolUse` is **fail-closed**: any non-zero exit (including 2) or crash denies the call; JSON `permissionDecision: "deny"` also works. Timeouts fall through to normal permissions. | Exit 2 blocks in both. Every allow path, including "no spec found, warning only", must exit 0, or Copilot blocks it. |
| Can the prompt hook block? | **No.** Copilot ignores command-hook output for `userPromptSubmitted`. | Parked: the PII prompt screen is not built for now. If it returns, it only needs to block Claude, since it exists to send PII work *to* Copilot. |
| Plugin-shipped hooks? | Copilot CLI: yes (`hooks.json` in the plugin). VS Code: agent plugins can bundle hooks, with known gaps. | Register hooks in the repo's `.claude/settings.json` (written by bootstrap-repo), not only in the plugin, so all three agents see them. |
| Status | VS Code hooks are Preview; Claude/Codex harnesses are switched off under Copilot enterprise-managed settings. | Re-check on each VS Code release; CI stays the backstop. |

## Still to test by hand

Run on a developer machine once protect-tests exists (it cannot be run from a cloud container):

1. VS Code, Copilot agent mode: ask it to edit a file under a locked `tests/`. Expect a block with our message.
2. Same in Copilot CLI, and once with a prompt that makes it use `apply_patch`.
3. Ask both to run `databricks bundle deploy -t prod`. Expect guard-bash to block.
4. Confirm Copilot expands `${CLAUDE_PROJECT_DIR:-.}` in the hook command from `templates/claude-settings.json`
   (if it runs commands without a shell, the hook path must become relative).
5. Record the exact `tool_input` payloads (log stdin to a temp file) and add them as fixtures to the hook tests.

## Hand test results

2026-10-26, VS Code Copilot agent mode on macOS, in a sandbox repo made with Lockstep 0.1.0 plus the shim fix:

| Case | Result |
|---|---|
| 1. Edit a locked test | **Pass.** The hook blocked it with the "BLOCKED by lockstep" message. |
| Hook finds Python | **Failed, then fixed.** `python3` on PATH was the macOS system 3.9, and hooks ignore the editor's selected interpreter, so the shim blocked every edit. The shim now looks for python3.14 down to python3.11 first, plus `LOCKSTEP_PYTHON`. |
| 3. Prod deploy | Not reached: Copilot refused on its own, following AGENTS.md, before calling the hook. |
| Allowed edits pass | **Pass.** A README edit went through with no hook message. (Copilot refused an out-of-spec code edit on its own, following AGENTS.md.) |
| 2, 4, 5 | Copilot CLI, `apply_patch`, `${CLAUDE_PROJECT_DIR}` expansion on Windows, and payload capture: still to do. |

The model refusing first is the instructions working; the hooks are the backstop for when it doesn't.
