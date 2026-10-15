# Code Review Checklist

The 10 questions that catch 90% of production risk in this codebase.
Last updated: 2026-10-15. The PR template references this list.

## The List

1. **Groundedness**: does this change affect what answers are based on?
   If yes - where is the eval delta? (ADR-0007 makes this blocking.)
2. **Error paths**: new failure modes raise typed exceptions with
   `code` + `transient`? Or does something still raise bare `Exception`?
3. **Degradation**: if the new dependency fails, does the service walk
   down the ladder or fall off it?
4. **Blast radius**: which SLO can this move? Latency? Availability?
   Cost-per-answer? Say which in the PR.
5. **Secrets**: any new env var, log line, or metric label that could
   leak key material or user content?
6. **Cardinality**: new metric labels bounded-set? (user IDs and prompt
   text in labels = monitoring outage.)
7. **Async hygiene**: any blocking call added to the event loop path?
   (sync I/O in async handlers = latency cliff under load.)
8. **Timeouts**: new network call has an explicit timeout? Unbounded
   waits are outage fuel.
9. **Rollback**: if this is wrong, what's the undo? Config flip, one
   revision back, or "restore from backup" (last resort)?
10. **Docs**: does a runbook/ADR/doc page need to change with it?
    Code that behaves differently than its docs is a future incident.

## Red Flags (instant reject)

- Prompt strings inline in business code (bypasses eval gates +
  injection guards)
- `except Exception: pass` anywhere on a serving path
- Hardcoded version strings, magic numbers without units
- New dependency without justification comment in requirements.txt
- Migration touching a hot table without a lock-expectation note

## Green Flags (review fast)

- Tests that pin a contract (probe semantics, error envelopes)
- Kill-switches instead of feature branches for risky paths
- Numbers with derivations (capacity doc links)
- ADR links when changing a decided thing
