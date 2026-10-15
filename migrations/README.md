# Database Migrations

Alembic-managed schema for Postgres: conversations, feedback,
documents registry, evaluation results.

## Policy (enforced by review, not tooling)

1. **Migrations are CODEOWNERS-gated** - `migrations/` requires owner
   review before merge. They are irreversible in production.
2. **Expand-contract only**: add nullable → dual-write → backfill →
   switch reads → drop old (next release). Never a breaking one-step.
3. **Forward-only in production.** `down()` exists for staging; prod
   rollback is the *next* migration (see rollback runbook).
4. **Migrations run as a pre-deploy Job**, never at pod boot - a
   crashing migration must not crash-loop the serving tier.
5. **Every migration file declares its blast radius** in the docstring:
   tables touched, rows affected estimate, lock expectations.

## Workflow

```bash
alembic revision -m "add_eval_results_table"     # autogenerate + review
alembic upgrade head                             # local/staging
alembic downgrade -1                             # staging only
alembic history                                  # audit trail
```

## Current Schema

| Revision | Date | Change |
|----------|------|--------|
| `001_initial` | 2026-01-01 | Conversations, feedback, document registry |
