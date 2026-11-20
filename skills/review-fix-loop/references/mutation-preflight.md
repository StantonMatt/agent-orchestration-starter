# Mutation and cache preflight

Read when changed behavior writes data. The implementation agent owns these decisions; advisory agents may gather evidence. Apply only relevant checks and mark non-applicable concerns briefly.

For every mutation, record a compact impact matrix in the implementation context:

| Field | Required decision |
| --- | --- |
| User behavior | The one visible action or state transition under review |
| Authoritative response | Response payload or persisted state that proves success |
| Exact entity cache | Exact query key to replace, invalidate, remove, or intentionally preserve |
| Collections and aggregates | Lists, filtered lists, counts, previews, search results, and related summaries affected |
| In-flight read risk | Whether an older request can overwrite mutation results and whether cancellation/abort is effective |
| Replacement-array risk | Whether the write can discard newer values and how authoritative state is refreshed before submission |
| Lifecycle references | Archived, hidden, inactive, cross-tenant, or otherwise stale IDs that must be filtered or preserved |
| Failure and retry | Cache remains correct, pending UI cannot create duplicate/out-of-order writes, and retry is safe |
| Permissions and tenancy | Capability, role, tenant boundary, and owner-only fields |
| Transaction and uniqueness | Atomic audit/data writes, lock scope, idempotency, uniqueness races, and bounded retry behavior |

## Client cache checks (TanStack Query and similar)

Apply these only when the repo uses a client query cache such as TanStack Query; skip this section otherwise.

- Inventory every query key that reads the mutated entity. Prefer a shared query-key factory when the repo has one.
- Use `setQueryData` only when the mutation response matches the exact cached schema and is authoritative. Invalidate lists, aggregates, or server-derived projections that are not fully represented by the response.
- Cancel an in-flight exact query before replacing cache only when its query function honors cancellation; otherwise ensure an older completion cannot overwrite the mutation result.
- Test the warm-cache path: read detail, mutate, then revisit before `staleTime` expires.
- Test failure, retry, rapid submission, dismissal while pending, and out-of-order completion when the action can overlap.
- For full-array PATCH/PUT contracts, refresh authoritative state before constructing the replacement array or use a server-side additive/removal operation.
- Verify tenant or user identity is encoded in cache ownership or that identity changes clear the relevant cache.

## After the checks

If the preflight exposes a correctness gap, fix and test it before starting the expensive fresh review. Repeat the affected matrix rows after a reviewer-driven fix that changes cache, transaction, permission, or concurrency behavior.

