<!-- Pull Request Template - enforces production review standards -->

## Description

<!-- What does this change do? Link to the issue it resolves (e.g., "Closes #123"). -->

Closes #

## Type of Change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing behavior to change)
- [ ] Infrastructure / deployment change
- [ ] Documentation change

## Production Impact Assessment

<!-- For a system serving 100M+ users, every change needs a blast-radius check. -->

- **Blast radius** (which components are affected):
- **Rollback plan** (how fast can we revert - reference the runbook):
- **Migration required**: [ ] Yes [ ] No
- **Feature flag / config-gated**: [ ] Yes [ ] No

## Testing

- [ ] Unit tests added or updated (`make test-unit`)
- [ ] Integration tests pass (`make test-integration`)
- [ ] Manual smoke test on local docker stack (`make up && make smoke`)
- [ ] Load test considered (does this change a hot path?)

## Quality Gates

- [ ] `make lint` passes (ruff + flake8 + black + isort)
- [ ] `make typecheck` passes (mypy)
- [ ] `pre-commit run --all-files` passes
- [ ] No secrets in diffs (gitleaps/detect-secrets clean)
- [ ] New/changed settings are documented in `.env.example`

## Documentation

- [ ] CHANGELOG.md updated for user-facing changes
- [ ] ADR created/updated for architectural decisions
- [ ] Runbook updated if operational behavior changed

## Reviewer Checklist

- [ ] Code follows the repository's production standards
- [ ] Error handling and logging follow structured patterns
- [ ] No synchronous blocking calls on the async event loop
- [ ] Rate limits / caching considered for new endpoints
