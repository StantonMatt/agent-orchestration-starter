---
name: babysit-pr
description: Use when the user asks to monitor, watch, or babysit a PR, or when full-send or full-stop reaches that step.
---

# Babysit PR

Own the PR through CI and review. Follow the project instructions and the calling
skill: [full-send](../full-send/SKILL.md) may merge after its gate;
[full-stop](../full-stop/SKILL.md) never merges. Standalone monitoring does not
authorize merging. Use full-send's proof and merge gate without assuming its
broader autonomy grant.

Use GitHub and `gh`. Check `gh auth status` before API work and the installed
command's `--help` before using unfamiliar flags.

## Handle current state

Read the live head, base, checks, reviews and discussions before waiting:

- `gh pr view <pr> --json url,state,isDraft,headRefOid,baseRefName,mergeable,mergeStateStatus,reviewDecision,autoMergeRequest,statusCheckRollup`.
- `gh pr view <pr> --comments` and `gh pr checks <pr>`.
- `gh run view <run-id> --log-failed` for failing workflow logs. Inspect the
  run's commit and event when the check result needs more context.
- Use `gh api` for review threads or queue state absent from the CLI output.
  Paginate lists with `--paginate`. Reply within the relevant thread and resolve
  it only after addressing the finding. Do not substitute a new comment for
  resolving a blocking discussion.

Verify checks cover the current PR head and base. Queue checks may use synthetic
commits; verify their relationship to this PR. Never accept an unrelated or
stale branch run. Evaluate bot results for the latest head; do not discard
unresolved human feedback merely because it predates a push.

Verify findings against the source. Fix real bugs and CI failures in scope;
distinguish infrastructure flakes from repository failures. Dismiss false
positives with a written reason. Wait for configured bots and handle their
findings.

Prove fixes, then run [review-fix-loop](../review-fix-loop/SKILL.md) before
committing or pushing them. Only `approved` allows publication; `needs user`
means stop and ask; `execution blocked` means stop and report. Batch follow-up
fixes into one deliberate push. Update the PR's proof and exact review-loop
summary line, then inspect the new head. Recheck full-stop's auto-merge and queue
protections before each push when it applies. Check public replies for secrets.

Fetch the base before declaring readiness or merging. Check ancestry and
conflicts yourself. Bring the branch up to date, prove meaningful conflict
fixes, review changed content and wait for green on the resulting head. If
another PR makes this one obsolete, ask before closing it unless closure was
explicitly authorized.

## Waiting

Handle actionable events first. Use one watcher per PR. Run
`gh pr checks <pr> --watch` as a background Bash command and act on its completion
notification. Do not write sleep or polling loops or launch a monitoring worker.
After completion, re-read the live head, checks, reviews and merge gate; a
successful watcher alone is not readiness. Start another only for new pending
checks, such as after a push. Stay quiet on events needing no action.

With no running checks, inspect reviews. Hand off if only external approval
remains. Do not invent CI requirements for a repository with no CI. If the
installed CLI cannot watch the relevant checks, report that limitation.

Never post "still waiting" comments. Stop at full-send's gate on the latest
head; merge only with authorization. Otherwise stop the task's background
watcher before handing off or asking the user. Report the PR link, head,
proof/review outcome, and readiness or blocker.

## Rate limits

On API HTTP 429, inspect headers with `gh api --include`. Honor `Retry-After`
and the rate-limit reset headers when supplied. Do not restart a rate-limited
watcher or switch endpoints in a tight loop. Arrange one delayed retry through
the harness if supported; otherwise report the reset time and blocker.

Adapted from [t3dotgg/tstack](https://github.com/t3dotgg/tstack) (MIT); see [../../THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md).
