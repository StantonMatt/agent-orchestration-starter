# Optional Codex CLI workers

This route is optional. Native Claude Code agents need no Codex installation. Use it only when the user has installed and authenticated Codex CLI. The commands and flags below were checked against version 0.171.0 with `codex exec --help` and `codex exec resume --help`; recheck help for another version.

1. Write a standalone brief with the file-writing tool to `~/.cache/agent-scratch/<project>/brief.md`. Follow [delegate-work](../SKILL.md), including the exact workspace, file scope, checks and cleanup rules. Prepare the scratch directory first.
2. Launch the command with Claude Code's Bash tool and `run_in_background: true`. Use literal absolute paths in place of the examples. The Bash call contains only the launcher command; never interpolate brief prose into shell or pass it as a quoted command argument.

```bash
codex exec --cd /absolute/path/to/repo --sandbox workspace-write --model '<your-codex-model>' -c 'model_reasoning_effort="<your-reasoning-effort>"' -c 'sandbox_workspace_write.network_access=false' -c 'web_search="disabled"' --json --output-last-message /absolute/path/to/scratch/report.md - < /absolute/path/to/scratch/brief.md
```

Use `--sandbox read-only` for research. Keep network access off unless the task needs it; for needed shell network access in the write sandbox, change the explicit `sandbox_workspace_write.network_access` setting to `true`. Choose a model and reasoning effort supported by the user's Codex setup. Do not use sandbox bypass flags.

`--json` emits progress events, including the session ID. Retain that ID and the Bash task handle. `--output-last-message` (short form `-o`) saves the final response; it is not the full event log. Wait for the completion notification. Do not detach with shell operators, poll in a loop or launch a second copy after an uncertain result.

For a follow-up, write a new brief file and resume the exact session that wrote the code. Keep the same workspace and sandbox. Options for the outer `exec` command go before `resume`:

```bash
codex exec --cd /absolute/path/to/repo --sandbox workspace-write -c 'sandbox_workspace_write.network_access=false' -c 'web_search="disabled"' resume <session-id> --json --output-last-message /absolute/path/to/scratch/follow-up-report.md - < /absolute/path/to/scratch/follow-up.md
```

Use the session ID rather than `--last` so another task cannot be resumed accidentally. Do not use `--ephemeral` when follow-ups will need the session. Use a fresh session for a different task; the mandatory review loop still uses fresh native `reviewer` agents.

Read the full report, inspect the actual diff and re-run key checks. A successful process exit does not prove the assignment is correct. On failure, inspect partial work and task-owned processes before replacing the worker. Apply the main skill's supervision and cleanup rules on Linux and macOS; sandbox behavior depends on the host and does not replace the file allowlist.
