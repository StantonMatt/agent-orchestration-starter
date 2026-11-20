---
name: review-fix-loop
description: Scope and preflight uncommitted changes, review and fix within a bounded round budget, and reach an explicit approved outcome before committing or pushing. Use before publishing task changes or when asked to review and repair uncommitted changes.
---

# Review fix loop

The implementation agent owns scope, fixes, verification, the ledger and outcome. Reviewers stay read-only and never launch agents or this loop. Only **approved** permits an otherwise-authorized commit or push.

Invoke `/review-fix-loop` in Claude Code, optionally `serial` or `parallel`. These are agent preferences, not script flags. `serial` disables advisory and fix workers; an independent reviewer is still required. `/path/to/review-fix-loop` below means this skill's installed base directory.

## Budget and grades

- Default: **3 rounds total**. If round 3 ends with an evidenced blocker or should, extend to **5** yourself when more rounds are likely to resolve it. The user may request more. Execution failures are not completed rounds; retain the budget and ledger when retrying.
- Stop early at an approved round with only nits. Declined nits and comment/doc/format-only fixes need no new round.
- **blocker:** the intended case is wrong. **should:** a real bug callers will hit within intent. Security or data-loss defects in changed behavior are at least should. **nit:** everything else.
- Re-grade findings yourself. Another path, a rare case or a small cost is a nit, subject to the security/data-loss floor.

## Reviewer route

Use a **new, never-resumed `reviewer` agent for every round**, Opus 5.5 at xhigh, through the Agent tool. Follow [native-reviewer](references/native-reviewer.md) for briefs, saved evidence and validation. Never substitute your own review or switch reviewers to evade findings. Missing agents or unavailable required settings are execution blockers.

## Scope and preflight

Start with `git status --short`. State intended behavior and out-of-scope work in 1–2 sentences. Record covering checks and missing or pre-failing checks in a round-1 brief outside the repo. Estimate all staged, unstaged and untracked non-ignored changes:

```bash
python3 /path/to/review-fix-loop/scripts/tree_fingerprint.py --repo /path/to/repo estimate
```

Read errors, file paths, added/removed lines and binary-file counts. Staged and unstaged line counts are summed, so a staged edit undone in the working tree still counts. Classify production/test paths yourself. About 500 production or 1,200 total changed lines warns; about 800 production or 1,500 total deserves closer attention. These are reviewability signals, not gates. Explain why the coherent authorized change is reviewable. Never stash, discard, commit or mechanically split the user's tree to meet a count. Ask only if scope or authorization is unclear.

Round 1 covers the **whole staged, unstaged and untracked diff**, including interactions. Disclose unrelated changes and preserve them. Scope errors do not prove a small or approved diff. Complete applicable tests and relevant integration/browser checks first. For changed writes, complete [mutation and cache preflight](references/mutation-preflight.md); refresh affected decisions after fixes.

For a large change (about 800 production or 1,500 total changed lines), run a read-only advisory sweep before round 1 unless the user asked for `serial`. It is optional for smaller multi-area changes or changes touching auth, permissions, security, money or migrations. Follow [parallel-work](references/parallel-work.md), validate centrally and integrate minimal fixes before authoritative round 1. No later trickle sweeps.

## Rounds and ledger

1. Keep the brief, snapshots, reports and ledger outside the repo under `~/.cache/agent-scratch/<project>/reviews/`. Ledger entries have stable ids (`S1`, `S2`, …), round, reviewer and implementer grades, claim, evidence, replies, open/resolved status and outcome: `fixed`, `disagree: <evidence>` or `declined: <one line>`. Declined or disputed items return only with new evidence.
2. Freeze writers. Capture the fingerprint and save enough diff/content evidence to compare the next round with this reviewed tree. Round 1 gets a fresh reviewer with the brief and policy, without implementation conversation or advisory history.
3. Read the whole final report. Verify the after-fingerprint and validate every finding. Re-grade, fix agreed issues and update the ledger. Disagree with evidence. An item still disputed after two evidence-based replies across rounds goes to [tiebreak](#tiebreak).
4. Prefer deleting or narrowing over new locks, caches, helpers or options. Fix the described case; fix siblings only when the same defect is in **changed code**. Add one focused regression only when intent needs it. Decline out-of-scope work or nits in one line and list follow-ups. Scoped fix workers use [delegate-work](../delegate-work/SKILL.md).
5. Run affected checks and the scope estimate again, including untracked files. Cut review-driven growth first; reassess before adding machinery.
6. Start another round within budget when a blocker/should remains, behavior changed or approval does not cover the current behavior diff. Comment/doc/format-only fixes and declined nits need none.
7. Rounds 2+ use a new reviewer with the round-1 brief, ledger and exact delta since the **previous reviewed tree**, including staged-only and untracked changes. Review open ids and changed code only. Mark every old id resolved or still open. New findings must be in changed code; read surrounding context as needed and review nested fallback paths fully. Never resume a reviewer with SendMessage.

## Review policy

Hold to the smallest change. Flag code, tests or guards intent does not need. Skip style unless it hides a bug. Use the grades above. Report every finding within the round's scope with concrete evidence and state incomplete coverage. Required output:

```text
VERDICT: APPROVE or VERDICT: CHANGES
S<n> [blocker|should|nit] <file>:<line> <claim>. Fix: <suggestion>
```

Choose one verdict on the first line. Keep stable ids; new ids follow the ledger's highest id. Rounds 2+ also mark old ids `S<n> resolved` or `S<n> still open: <reason>`. APPROVE means no open blocker/should; nits may accompany APPROVE.

## Stable-tree rule

From before-fingerprint through after-fingerprint, no agent may edit, stage, generate, commit or delete review inputs. No fix workers may run. Concurrent verification requires isolated outputs, caches and databases. Run these exact commands on the same repo, retaining the captured digest outside it:

```bash
python3 /path/to/review-fix-loop/scripts/tree_fingerprint.py --repo /path/to/repo capture
python3 /path/to/review-fix-loop/scripts/tree_fingerprint.py --repo /path/to/repo verify <captured-sha256>
```

Verify immediately after review and again before applying fixes or starting the next round. Expected fixes then require a fresh capture. Unexpected changes invalidate the round: stop writers and repeat it. A changed or unreadable fingerprint invalidates any verdict; repeated inability to freeze is an execution blocker.

The fingerprint covers repo identity, HEAD (or no commits), the index, changed tracked paths and untracked non-ignored paths, modes and bytes. Ignored files are excluded. The script does not change the worktree, index contents or refs. Git itself may still touch split-index timestamps or fetch missing objects in a partial clone. Paths marked assume-unchanged or skip-worktree are not checked; clear those flags before review. It refuses changed directories/special files rather than claiming recursive submodule or nested-repo coverage. Report that limitation; matching hashes do not excuse missing review coverage or authorize concurrent writes.

## Tiebreak

After two evidence-based replies fail to settle an item, consult two fresh read-only `advisor` agents in parallel: the default Fable 5.2 at xhigh and a second `advisor` with Agent `model: "opus"` (Opus 5.5 at xhigh). Give both the neutral round-1 brief, finding, both sides' arguments, evidence and relevant paths. Ask which side is right and what grade the item deserves. Weigh their evidence, not votes. If one cannot run, disclose that and use the other.

- **Clear ruling sides with the reviewer:** use the ruling's grade; fix a blocker/should and review again within budget.
- **Clear ruling sides with you:** mark `declined: tiebreak, <one line>` and list the downgraded finding in the report.
- **Unclear ruling or neither advisor can run:** needs user. Present the evidence; do not manufacture consensus.

A tiebreak is not a round and cannot approve the loop. Its ruling stands unless new evidence appears.

## Outcomes and report

Read the whole final message. Missing output, incomplete coverage, ambiguous text, execution failure or stale inputs cannot approve. Findings outrank clean-sounding prose; silence is not approval.

- **approved:** explicit reviewer APPROVE covers current behavior, with no open blocker/should and no concern of your own.
- **needs user:** unclear/unavailable tiebreak or budget ends with an open blocker/should. Show both sides in 2–3 lines each. A nits-only round without explicit approval also stops here. Do not commit or push.
- **execution blocked:** review cannot complete validly. Report saved artifact paths, relevant error text and coverage limits. Do not commit or push.

Report rounds, model, diff size before/after including untracked files, fixes, declines with reasons, validation and outcome. List downgraded or declined reviewer blocker/should findings first, with both grades and evidence. Give short milestone updates while agents run; use completion notifications, not polling.

When filing or updating a pull/merge request, include actual values in this line:

`Reviewed with review-fix-loop: <N> rounds with <model>. Verdict: <approved | not approved — open: S<ids>>[; downgraded: S<ids>]`
