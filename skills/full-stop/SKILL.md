---
name: full-stop
description: Use when the user says "full stop".
---

# Full Stop

Read [full-send](../full-send/SKILL.md) and follow its workflow, proof, testing
permission, review-fix-loop and [babysitting](../babysit-pr/SKILL.md) rules.
A clear "full stop" request authorizes that work without a separate "full send"
request. If the user did not clearly ask, do not assume this autonomy.
The overrides below replace full-send's merge permission and final steps.

## No merging

You may commit, push, rebase, fix conflicts and use `--force-with-lease` on this
task's branch after the required proof and review. Never merge, enable
auto-merge, enter a merge queue, push to the default branch, bypass protection,
or delegate those actions.

For an existing PR, before work begins, disable auto-merge with
`gh pr merge <pr> --disable-auto` and remove the PR from any merge queue.
Inspect `autoMergeRequest` with `gh pr view <pr> --json autoMergeRequest,id`.
Inspect `mergeQueueEntry` through `gh api graphql` using the PR's node ID; if
queued, use its `dequeuePullRequest` mutation or GitHub's leave-queue control.
Do not assume disabling auto-merge also removes an existing queue entry.
Re-read both states to confirm auto-merge is off and the PR is not queued;
an API success alone is insufficient. Never call a merge command without
`--disable-auto` to cancel merging.

Recheck before every push, including delegated pushes, and at handoff. Report
changes to those settings. If you cannot prevent automatic merging, stop and
report the blocker before proceeding.

## Handoff

Use full-send's merge gate as the readiness check. Proof and review must cover
the final diff; recheck behavior changes and meaningful conflict fixes.

Fetch the base and check the live PR's head, base, checks, reviews and
mergeability using babysit-pr's commands. Mark it ready with `gh pr ready <pr>`
after proof and review; use `gh pr ready <pr> --undo` while work is in progress.
Confirm it is open, not a draft, and cannot merge automatically.
If someone else merged it, report that instead.

- **Ready to merge:** the gate passes. Leave the PR open and unmerged.
- **Waiting for required approval:** only human approval remains; verify that
  this is the actual blocker.
- **Blocked:** explain the blocker, attempts and what is needed. Ask the user
  when a decision is needed, including review-fix-loop's `needs user` outcome.

Stop any task-owned background watcher before handoff or a question. Report
the PR link, final head, verdict, proof, reviewer outcome and remaining risks;
explicitly state whether it remains open and unmerged. Stop temporary task
processes and tabs; report any retained worktree or persistent resources. Keep
the worktree while the PR is open; remove it and the local branch after merge
or abandonment only when clean, following the project instructions.

Adapted from [t3dotgg/tstack](https://github.com/t3dotgg/tstack) (MIT); see [../../THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md).
