# Native reviewer

In T3, Claude only with a Claude main session keeps this native Agent route;
see [T3 review runtime](t3-runtime.md) for wait and isolation limits.

Use Claude Code's Agent tool with a fresh `reviewer` agent, Opus 5.5 at xhigh. Never use an implementing agent, resume a reviewer or continue it with SendMessage. The reviewer stays read-only and does not start agents. If the required agent or settings are unavailable, report execution blocked.

## Prepare and capture

1. Stop all writers. Finish applicable verification before review. Put the round-1 intent/scope/checks brief and review artifacts outside the repo under `~/.cache/agent-scratch/<project>/reviews/`.
2. Save the current HEAD identity, staged and unstaged binary patches (disable external diff and text conversion), and copies of untracked non-ignored files with their original paths and modes outside the repo. Preserve index-only changes too: a combined `git diff HEAD` is insufficient. Keep this reviewed snapshot until a valid next round replaces it. The fingerprint is a digest, not a recoverable snapshot.
3. Capture immediately before launching the reviewer and retain the single digest:

   ```bash
   python3 /path/to/review-fix-loop/scripts/tree_fingerprint.py --repo /path/to/repo capture
   ```

   A capture error blocks the pass. The script does not write inside the repo or mutate the index. Changed directories, including dirty submodules and untracked nested repositories, are refused; do not claim those were fingerprinted recursively. Ignored dependencies are outside its coverage, so keep them stable too.

## Fresh reviewer brief

Give the exact repo path, applicable repository instructions, the round-1 brief and [main skill](../SKILL.md) policy. Round 1 has no previous findings, advisory history or implementation conversation. For later rounds, include the full ledger, previous reviewed snapshot and exact delta from that snapshot, not merely the current diff against HEAD. Materialize readable delta artifacts outside the repo before freezing; include added, removed and changed untracked files and staging-only changes.

Include this instruction verbatim:

```text
Review only. Do not edit, stage, generate, commit, push, delete or start agents/reviewers.
Use GIT_OPTIONAL_LOCKS=0 for Git reads so they cannot refresh the user's index.
Run checks only if their outputs cannot change review inputs. Read unchanged context as needed.
Read the supplied context and all referenced artifacts before reviewing.
Round 1: review the entire staged, unstaged and untracked diff with no history.
Rounds 2+: check open ids and changed code only; mark each old id S<n> resolved or
S<n> still open: <reason>. New findings only in changed code; nested fallback paths fully.
A declined/disputed item may return only with new evidence.
Hold to the smallest change; flag code, tests or guards the intent does not need.
Skip style unless it hides a bug. blocker = intended case wrong; should = real bug
callers will hit within intent; nit = everything else. Security/data-loss defects in
changed behavior are at least should. Another path, rare case or small cost is a nit,
subject to that security/data-loss floor. Report every finding within this round's scope.
First line VERDICT: APPROVE or VERDICT: CHANGES; then one line per finding:
S<n> [blocker|should|nit] <file>:<line> <claim>. Fix: <suggestion>
Keep stable ids; new ids follow the highest ledger id. APPROVE means no open blocker/should;
nits can accompany APPROVE. Include concrete evidence and state incomplete coverage.
```

Launch in the background, retain the handle and wait for completion notification. Do not poll or use sleep loops.

## Validate and continue

Save and read the complete final report outside the repo. Verify against the captured digest immediately after completion:

```bash
python3 /path/to/review-fix-loop/scripts/tree_fingerprint.py --repo /path/to/repo verify <captured-sha256>
```

Exit 0 means unchanged; exit 1 means changed; exit 2 means inspection failed. A mismatch aborts the round regardless of verdict. Stop writers, inspect the unexpected change and repeat with a fresh reviewer. Missing output, failure or incomplete review coverage invalidates the pass even if the fingerprint matches. A reviewer may report tests it could not safely run; distinguish those verification limitations from unread review scope. The implementation agent owns test execution.

Before applying fixes, verify once more. Before the next round, verify against the last digest again if no fixes were expected. If intentional fixes changed the tree, inspect that delta against the saved reviewed snapshot, complete affected checks and capture a new digest. Every later pass gets fresh before/after checks and a new reviewer. Keep the round-1 brief, ledger and last valid reviewed snapshot; never use an invalid pass as the next delta's base. Apply the main skill's budget and outcome rules.
