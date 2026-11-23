# T3 review runtime

Keep authoritative reviews on the starter's existing routes: Codex uses
[codex-reviewer](codex-reviewer.md), including `codex exec review`, explicit
read-only settings and fresh fingerprints; Claude only with a Claude main
session uses [native-reviewer](native-reviewer.md). T3 provider authentication
does not prove the local Codex CLI is authenticated. Verify it without printing
credentials. An unavailable required route is an execution blocker, subject
only to the global setup fallback rules. A Codex orchestrator never switches
to Claude only, and no route may switch to evade findings.

For the CLI process, use a tracked background handle and retain its report,
events and stderr paths. Claude Code uses Bash `run_in_background: true`, never
shell detachment. If T3 offers `t3_background_wait`, give it the returned
background handle and follow its continuation. Codex uses its harness's process
wait. Do not write polling/sleep loops, start a second review after a wait
timeout, or resume a reviewer. Timeout does not establish process cleanup.

Delegated read-only advisory sweeps, tiebreaks and scoped fix workers follow
[T3 Code](../../delegate-work/references/t3-code.md). Give every advisory pass
or recheck a fresh `delegate_task`, complete brief and explicit restrictions;
never continue its backing thread. A role or plan mode does not establish the
CLI's read-only sandbox. Advisory approvals and tiebreaks cannot approve the
authoritative loop. Stop fix workers before capturing review inputs.

Keep the main skill's whole-tree scope, round budget, snapshot/delta artifacts,
stable-tree verification, ledger and explicit verdict rules. After failures or
cancellation inspect partial work and task-owned process handles before retrying.
No T3 shared-slot, memory-limit or subtree-cleanup guarantee is implied.
