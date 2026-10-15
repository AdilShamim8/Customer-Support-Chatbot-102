# ADR-0001: Record Architecture Decisions

- Status: Accepted
- Date: 2026-10-15
- Deciders: @AdilShamim8

## Context

Engineering choices that outlive the code review that approved them
(vector store selection, streaming transport, rate-limit placement)
are invisible to future maintainers. When they need changing, nobody
knows what constraints the original choice satisfied - so changes are
either blocked by fear or made blindly.

## Decision

Record every architecturally significant decision as an ADR in
`docs/architecture/adr/`, numbered sequentially, with Status
(Proposed / Accepted / Superseded-by-ADR-XXXX), Context, Decision,
Consequences, and the alternatives genuinely considered.

## Consequences

- Decisions become auditable; "why is retrieval hybrid?" has a URL.
- Superseding requires writing the new ADR that references the old -
  cheap ceremony that prevents silent architecture drift.
- ADRs are immutable once Accepted; corrections ship as new ADRs.
