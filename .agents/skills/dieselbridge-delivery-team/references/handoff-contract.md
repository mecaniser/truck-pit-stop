# Handoff contract

Use this compact record whenever ownership changes.

```markdown
Board ID:
From / To:
User outcome:
Scope completed:
Scope explicitly not completed:
Contract or migration impact:
Acceptance evidence:
Known failures / risks:
Branch / PR / environment:
Next required action:
Return condition:
```

For a frontend/backend contract, also include request/response examples,
authorization and tenant rules, error codes, idempotency/concurrency rules,
compatibility, and the shared test fixture.

For QA, include exact setup, actions, expected result, actual result, logs/trace/
screenshot location, and whether test data was mutated.

For release, include merge SHA, migration result, deployment time, health/canary
result, observed metrics, rollback trigger, and follow-up owner.
