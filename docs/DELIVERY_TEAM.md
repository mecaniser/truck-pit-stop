# DieselBridge Core Delivery Team

This is a project-driven team, not a collection of disconnected chat personas.
Each role owns a decision boundary and hands work off through explicit evidence.

## Core roles

| Role | Receives | Accountable output | Hands off to |
|---|---|---|---|
| Product & Delivery Lead | Ideas, defects, business goals, cross-team status | Prioritized board item, user outcome, acceptance criteria, release decision | Architecture or the smallest capable implementation owner |
| Architecture & API Contracts | Cross-layer work, schemas, migrations, integrations, concurrency | Versioned API/data contract, compatibility and rollout plan, work split | Backend, Frontend, Security |
| Backend & Integrations | APIs, services, data, workers, payments, external integrations | Implemented contract, migrations, backend tests, operational notes | Frontend when UI consumes it; QA when complete |
| Frontend & UX | Staff/customer/driver UI, accessibility, responsive behavior | Contract-backed UI, component tests, production build, interaction evidence | QA |
| Security & Identity | WorkOS, tenant isolation, permissions, secrets, payments, privacy | Threat review, negative tests, security decision and remediation | Owner on failure; QA/Release on pass |
| QA Gatekeeper | Acceptance criteria, regression, browser and API verification | Independent GO/NO-GO with reproducible evidence | Owner on failure; Release on pass |
| Release & Reliability | CI, migrations, deployment, observability, rollback, canary | Merge/deploy record, health evidence, rollback readiness | Product & Delivery Lead |

The Product & Delivery Lead is the only normal intake point. It routes the item;
the user should not need to decide whether a defect belongs to frontend, backend,
security, or QA.

## App task map

These pinned DieselBridge tasks are the stable role inboxes:

| Role | App task ID |
|---|---|
| Product & Delivery Lead | `019fee3d-b5af-7b90-8274-df8b546c176a` |
| Architecture & API Contracts | `019f87d6-2531-75d0-9501-d71e4c500b9d` |
| Backend & Integrations | `019fb482-51df-73d3-9b59-364f84d0e74c` |
| Frontend & UX | `019f8aee-fa34-75b1-89ad-361ad8a45d2e` |
| Security & Identity | `019fe98f-bd57-78b1-8769-f9a8876930fb` |
| QA Gatekeeper | `019fed9f-cce5-7853-8862-adcbd9dc6630` |
| Release & Reliability | `019f8ab3-5084-72b1-bac8-aa71d3f6539b` |

Send new work to Product & Delivery Lead. Direct role assignment is appropriate
only for a well-formed board item that already names its contract and acceptance
criteria. Role tasks load this repository's `AGENTS.md` when resumed.

## Required lifecycle

```text
Inbox -> Discovery -> Ready -> In Progress -> Review -> QA/Security ->
Ready to Release -> Released -> Done
```

`Blocked` is a visible state, not a parking lot. Every blocked item must name the
blocking condition, who can resolve it, and the next safe action.

## Contract-first handoff

When frontend and backend must coordinate, Architecture & API Contracts records:

- request and response shape;
- authorization and tenant boundary;
- validation and error semantics;
- idempotency/concurrency behavior;
- migration and backwards-compatibility requirements;
- test fixtures or mocks usable by both sides.

Frontend may proceed against the agreed fixture while backend implements the
contract. Contract changes return to Architecture instead of being negotiated
silently in implementation code.

## Failure routing

| Failure | First owner |
|---|---|
| Incorrect product behavior or missing acceptance criterion | Product & Delivery Lead |
| Cross-layer mismatch or breaking contract | Architecture & API Contracts |
| API, data, worker, payment, or integration defect | Backend & Integrations |
| Rendering, navigation, form, accessibility, responsive defect | Frontend & UX |
| Authentication, authorization, tenant leakage, secret/privacy concern | Security & Identity |
| Flaky/missing automation or unreproducible acceptance result | QA Gatekeeper |
| CI, migration, deployment, monitoring, rollback failure | Release & Reliability |

## Escalation to the product owner

Escalate only when:

- two plausible product behaviors would create materially different outcomes;
- external credentials, MFA, vendor approval, or production authority is needed;
- a destructive or irreversible action is required;
- evidence cannot identify a safe resolution after root-cause investigation.

Routine retesting, selecting the technical owner, reproducing regressions, and
coordinating frontend/backend contracts remain the team's responsibility.
