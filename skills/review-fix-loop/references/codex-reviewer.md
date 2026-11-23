# Codex reviewer

Use this route in **Codex + Claude** and **Codex only**. Every round uses a fresh,
never-resumed `codex exec review` process, `gpt-6.1-sol` at high, read-only.
An installed, authenticated Codex CLI is required. These flags were checked with
version 0.171.0: `codex exec review --help`, `codex exec --help` and
`codex review --help`. Recheck help for another version. Config keys are defined
in the [matching CLI schema](https://github.com/openai/codex/blob/rust-v0.171.0/codex-rs/core/config.schema.json).

In T3, also follow [T3 review runtime](t3-runtime.md); this CLI remains the
authoritative Codex route.

## Prepare and capture

1. Finish applicable checks and stop all writers. Keep review artifacts outside
   the repo under `~/.cache/agent-scratch/<project>/reviews/`, one directory per pass.
2. Save the HEAD identity, separate staged and unstaged binary patches without
   external diff or text conversion, and copies of untracked non-ignored files
   with paths and modes. Preserve index-only changes. Follow
   [native-reviewer](native-reviewer.md) for snapshot and delta requirements.
3. Write `round-context.md` with the absolute repo path, applicable instructions,
   round number, round-1 intent/scope/checks brief, and a frozen ledger copy.
   Round 1 has no implementation conversation or advisory history. Later rounds
   also name the previous valid reviewed snapshot and exact delta artifact paths,
   including untracked and staging-only changes. Keep these files until the loop ends.
4. Copy the verbatim policy block from [native-reviewer](native-reviewer.md) into
   `policy.txt` beside the context file. Reference it from the context file and
   require reading it and all referenced artifacts before reviewing.
5. Capture immediately before launch and retain the digest outside the repo:

   ```bash
   python3 /path/to/review-fix-loop/scripts/tree_fingerprint.py --repo /path/to/repo capture
   ```

A capture error blocks the pass. Keep ignored dependencies stable too. The
fingerprint is not a recoverable snapshot and does not cover ignored files.

## Launch once

Replace the literal absolute paths below. Keep the policy and brief in files;
never interpolate their prose into shell code. The short, fixed developer
instruction points to the context file. Do not add a positional prompt alongside
`--uncommitted`. `review_model` prevents a configured review override changing
the selected model; `developer_instructions` applies only to this invocation.

```bash
GIT_OPTIONAL_LOCKS=0 codex exec review --uncommitted --model gpt-6.1-sol \
  -c 'review_model="gpt-6.1-sol"' -c 'model_reasoning_effort="high"' \
  -c 'sandbox_mode="read-only"' \
  -c 'developer_instructions="Review only. First read /absolute/path/to/scratch/round-context.md and all referenced artifacts. Follow its policy and round scope. Do not edit, stage, generate, commit, push, delete or start agents or reviewers. Your final message must start with VERDICT: APPROVE or VERDICT: CHANGES, followed by one line per finding in the policy format."' \
  --ephemeral --json --output-last-message /absolute/path/to/scratch/report.md \
  > /absolute/path/to/scratch/events.jsonl 2> /absolute/path/to/scratch/stderr.log
```

Run from the exact repo directory. From Claude Code, use the Bash tool's
`run_in_background: true` and act on its completion notification; a foreground
call is capped at 10 minutes. From a Codex orchestrator, use a generous host
timeout and retain the yielded process handle until completion. Never detach,
poll with sleeps, start a duplicate after an uncertain result or resume a reviewer.

## Validate and handle failure

Verify immediately after completion, then read the whole final report and
inspect JSON events and stderr for execution errors:

```bash
python3 /path/to/review-fix-loop/scripts/tree_fingerprint.py --repo /path/to/repo verify <captured-sha256>
```

Verify again before fixes. Apply [native-reviewer](native-reviewer.md)'s validation
and snapshot rules and the [main skill](../SKILL.md)'s budget and outcomes.
Exit zero alone cannot approve. Missing output, incomplete coverage, a killed
process, execution failure or changed/unreadable fingerprints invalidate the pass.

For a Claude orchestrator in **Codex + Claude**, a launch, sign-in, plan or quota failure switches the
session to **Claude only**. Quote the error and rerun the same round with a fresh
native `reviewer`, the same scope/context and fresh fingerprints. A transient
HTTP 429 / "Rate limit exceeded" or capacity/overload error requires waiting a few
minutes and retrying once first; switch only if that also fails. A Codex orchestrator
reports the blocker instead. Findings, stale trees and other execution errors
retain normal failure handling. Never switch reviewers to evade findings.
