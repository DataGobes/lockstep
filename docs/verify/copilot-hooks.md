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
| Can the prompt hook block? | **No.** Copilot ignores command-hook output for `userPromptSubmitted`. | Fine: screen-pii exists to send PII work *to* Copilot, so it only needs to block Claude. |
| Plugin-shipped hooks? | Copilot CLI: yes (`hooks.json` in the plugin). VS Code: agent plugins can bundle hooks, with known gaps. | Register hooks in the repo's `.claude/settings.json` (written by bootstrap-repo), not only in the plugin, so all three agents see them. |
| Status | VS Code hooks are Preview; Claude/Codex harnesses are switched off under Copilot enterprise-managed settings. | Re-check on each VS Code release; CI stays the backstop. |

## Still to test by hand

Run on a developer machine once protect-tests exists (it cannot be run from a cloud container):

1. VS Code, Copilot agent mode: ask it to edit a file under a locked `tests/`. Expect a block with our message.
2. Same in Copilot CLI, and once with a prompt that makes it use `apply_patch`.
3. Ask both to run `databricks bundle deploy -t prod`. Expect guard-bash to block.
4. Record the exact `tool_input` payloads (log stdin to a temp file) and add them as fixtures to the hook tests.
