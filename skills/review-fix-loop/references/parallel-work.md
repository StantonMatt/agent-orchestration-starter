# Parallel work

Read when advisory triage or disjoint fixes would save time. Follow [delegate-work](../../delegate-work/SKILL.md) for briefing, supervision and integration.

Use parallel help only for at least two useful, non-overlapping scopes when expected savings exceed startup and integration costs. Separate data, permissions and tests can qualify. Keep small single-scope changes and shared-schema work serial. Explain briefly if a requested split is unsafe.

## Advisory triage

Use this before authoritative round 1: required for a large change, optional for smaller sensitive or multi-area changes, unless the user asked for serial. It neither consumes nor extends the round budget.

Start only the fresh read-only `reviewer` agents needed for coherent path scopes, usually two to four. Add a cross-cutting scope for auth, permissions, security and data integrity when touched. Give each the [main skill](../SKILL.md) policy and an explicit prohibition on edits, staging, generation, deletion and starting agents. They gather evidence; the implementation agent owns scope and mutation/cache decisions.

Ask for all findings in scope with stable ids, grades, file, line, trigger and evidence. Hold to the smallest change; skip style unless it hides a bug. Keep advisory ids separate from the authoritative ledger. Round 1 receives no advisory history.

Collect results, validate centrally and integrate agreed fixes before authoritative round 1. Advisory agents cannot advance the loop or declare it approved.

## Fixes after an authoritative round

Use native `worker` agents only for genuinely disjoint findings. Give each an exact file allowlist and one finding or tightly coupled group. Request the smallest fix; siblings qualify only when the same defect is in changed code. Add one focused regression only when intent needs it. Keep shared schemas, generated files, lockfiles, migrations and cross-cutting fixes with one integrator. Preserve unrelated changes.

After completion, inspect the integrated diff, resolve overlaps centrally, refresh affected preflight decisions and verify. Estimate the scope again, including untracked files, and cut growth first. Freeze the tree and, when required within budget, start a fresh authoritative reviewer with the round-1 brief, ledger and delta. Later rounds check only open ids and changed code. Never run fix workers during authoritative review or substitute sharded approvals for its outcome.
