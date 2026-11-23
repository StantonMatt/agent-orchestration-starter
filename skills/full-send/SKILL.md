---
name: full-send
description: Use when the user says "full send".
---

# Full Send

Own the task from its current state to a merged PR. If the user did not clearly
request "full send", do not assume this autonomy.
[Full-stop](../full-stop/SKILL.md) authorizes the same workflow with its no-merge
overrides. Follow the project instructions, including delegation and review
ownership rules. This skill defines the flow, not who implements it.

The request authorizes commits, pushes, merging after the gate passes,
rebasing and `--force-with-lease` on this task's own branch, and the tests below.

## T3 Code

Inside T3, read [T3 Code](../delegate-work/references/t3-code.md). Its PR tools
and waiting rules override the `gh` and background watcher examples below.
Use available `pull_request_*` tools for PR operations and `ci_logs`/`ci_rerun`
for checks. Immediately link each PR created, taken over or pushed to with
`link_pull_request` (all stack layers with `link_pull_requests`); creation via
`pull_request_create` already links it. Report linking failures.

Only the orchestrator watches: after needed branch updates and pushes, call
`watch_pull_request` for requested monitoring or pending checks/reviews, follow
its continuation and end the turn. Do not poll, run `gh --watch`, or launch
monitoring workers. Children report the PR URL, head and checks/reviews to the
parent and never watch. Before final handback or asking for a decision, call
`unwatch_pull_request` on watched PRs. Watching never grants merge permission.
Keep the calling skill's proof, review and merge/no-merge gates.

## Testing permission

A "full send" request authorizes the test methods Proof needs without asking
first, replacing project ask-first or leave-testing-to-the-user rules for this
task. This includes computer use, browser automation, simulators and devices,
running the app or a dev server, screenshots and visual checks.

Follow rules about how to test: commands, fixtures and `heavy` if installed
still apply. Use the method that directly proves the change. This permission
covers only task tests; it does not authorize production changes, deleting user
data, unrelated external actions, or bypassing system approval prompts.

## Steps

1. **Prepare.** Inspect the checkout and preserve inherited work. On the default
   branch, create a task branch. With unrelated changes, use a worktree under
   `~/.worktrees/<repo>/<branch>`; do not carry those changes into the PR.
   Check `git remote get-url origin` and use SSH remotes. Fetch and bring the
   task branch up to date with its base before proof and review.
2. **Finish the change.** Complete the user's goal with the smallest change that
   works. Fix the case that happened, not every case that could.
3. **Prove it.** Observe the evidence described below.
4. **Review.** Use [review-fix-loop](../review-fix-loop/SKILL.md) before committing
   or pushing. Respect its round budget and extension rules. `approved` permits
   publication; `needs user` means stop and ask; `execution blocked` means stop
   and report. Never treat either as approval. Approval must cover the published
   behavior; follow the loop's rules for later changes.
5. **File the PR.** Use GitHub and `gh`; check `gh auth status` and the installed
   command's `--help`. Check `gh pr list --head <branch>` for an existing PR and
   inspect the final diff against its base. Follow repository title conventions.
   Open the description with the problem and resulting behavior, then briefly
   explain the solution. Include proof and the loop's exact summary line:
   `Reviewed with review-fix-loop: <N> rounds with <model>. Verdict: ...`.
   Include any required harness attribution using reported public names; never
   guess a model. Check public text and attachments for secrets.
   Push deliberately and batch fixes. Use `gh pr create --base <base>
   --head <branch> --title <title> --body-file <file>`, adding `--draft` while
   work is in progress. Use `gh pr edit <pr> --body-file <file>` to update proof.
   Mark ready with `gh pr ready <pr>` only after proof and review; use
   `gh pr ready <pr> --undo` to return to draft when needed.
6. **Babysit.** Follow [babysit-pr](../babysit-pr/SKILL.md) through CI and review.
   Prove and run review-fix-loop on follow-up fixes before their batched push.
7. **Merge.** Fetch and recheck the live head, base and merge gate. Base updates
   or conflict fixes that change reviewed content go back through proof, review
   and CI. Respect repository merge settings and recent merges. Use
   `gh pr merge <pr> --match-head-commit <reviewed-head>` with the permitted
   strategy (`--squash`, `--merge` or `--rebase`) when needed. Never bypass
   protection. A queue may defer merging; retain ownership until GitHub confirms
   `state=MERGED` with `gh pr view <pr> --json state,mergedAt,mergeCommit`.
8. **Clean up and report.** Stop task-owned temporary processes, watchers and
   browser tabs. After merge, remove its clean worktree with `git worktree remove`
   and `git worktree prune`, and delete its local branch from another checkout.
   Preserve uncommitted work. Report the PR, merge commit, proof, review outcome
   and decisions made for the user, plus persistent task resources or limits.

Keep ownership until merge or a real blocker. Follow babysit-pr's runtime-specific
watch route and resume on completion. If a merge queue still needs checks,
watch those checks; if an external queue decision alone remains, report it
without claiming a merge. Delegated children return status to the orchestrator.

## Proof

Proof is evidence observed in this session: command output, a reproduction or a
screenshot. Cover every change in the final diff.

- Reproduce the original failure, then observe the same reproduction pass.
- Run focused checks for touched behavior locally. Add a regression test when
  missing coverage materially affects confidence in the fix.
- When CI runs the full suites, let CI run them after the reviewed push; do not
  duplicate them locally. If CI is absent, unavailable or lacks that coverage,
  run the applicable full suites locally through `heavy` if installed.
- For UI/runtime changes, run the app and check the change in a browser the way
  the user will use it. Mocked tests alone do not prove the experience. Attach
  screenshots when useful and upload is available.

Follow repository integration and user-facing verification requirements.
If there is no way to prove the change, ask the user.

## Merge gate

All must hold on the latest head:

- Proof covers the diff, and review-fix-loop approved the published content.
- Required checks and applicable CI suites succeeded when the repository has CI;
  otherwise the applicable local suites passed. Verify checks cover the current
  head and base, not just the watcher exit code.
- Configured review bots finished; findings are fixed or dismissed with a written
  reason. No human review still requests changes.
- The branch is up to date with its base and the PR is open and ready. Live
  mergeability, required approvals, resolved blocking discussions and branch
  protection permit the merge. Unknown or checking states do not pass the gate.

## Asking the user

Ask in plain chat or use the harness's question tool if available. Include the
PR link (or say no PR yet), blocker, and options with the recommendation first.
Stop any task-owned background watcher before asking.

Ask only when you cannot continue alone: proof is unavailable; the merge gate
cannot pass; review-fix-loop returns `needs user`; the goal is materially
ambiguous; another PR makes this one obsolete; or the next action exceeds the
grant (production, user data deletion, unrelated changes outside the repository,
closing a PR, or force-pushing another branch). Decide routine details and report
them. Without an answer, preserve the blocked state and leave the PR open and
unmerged. Start the final message with the question; silence is not approval.

Adapted from [t3dotgg/tstack](https://github.com/t3dotgg/tstack) (MIT); see [../../THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md).
