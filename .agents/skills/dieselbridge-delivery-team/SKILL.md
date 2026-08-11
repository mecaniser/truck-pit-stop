---
name: dieselbridge-delivery-team
description: Govern DieselBridge product delivery from intake through release using accountable role routing, contract-first frontend/backend coordination, independent QA and security gates, and an evidence-backed project board. Use for any DieselBridge feature, defect, refactor, integration, security change, QA request, release, status review, backlog update, or request to assign or coordinate work across product, architecture, backend, frontend, security, QA, and reliability.
---

# DieselBridge Delivery Team

Route every request through one accountable delivery path and keep
`docs/PROJECT_BOARD.md` synchronized with repository and runtime evidence.

Read `AGENTS.md`, `docs/DELIVERY_TEAM.md`, and `docs/PROJECT_BOARD.md` before
acting. Read `references/handoff-contract.md` when handing work between roles.

## Workflow

1. **Intake.** Search the board, open PRs/branches, current diff, and relevant
   task history. Attach the request to an existing item or create one ID. Name
   the user outcome, acceptance criteria, priority, and one accountable owner.
2. **Route.** Send product ambiguity to Product & Delivery Lead. Send cross-layer
   contracts, migrations, or concurrency to Architecture & API Contracts. Route
   implementation to the smallest capable owner using `docs/DELIVERY_TEAM.md`.
3. **Contract.** Before parallel frontend/backend work, record request/response,
   auth and tenant boundary, errors, idempotency, compatibility, and fixtures.
4. **Implement.** Preserve unrelated changes. Use a focused branch/PR. Add the
   narrowest tests that prove the acceptance criteria and important failures.
5. **Gate.** Require independent QA for user-visible behavior and an independent
   Security gate for identity, tenant, payment, secret, or sensitive-data
   changes. Check the handoff record: a gatekeeper must not have implemented or
   directed the change. Use the fallback assignments in `docs/DELIVERY_TEAM.md`
   when QA or Security is the implementing owner. A gate failure returns to the
   responsible owner with reproduction evidence.
6. **Release.** Require the repository quality gates, migration declaration,
   runtime acceptance, rollback signal, and post-deploy observation appropriate
   to risk. Use Playwright for changed critical journeys.
7. **Close.** Mark Done only after required merge/deploy evidence exists. Record
   unresolved external approvals as Blocked, not Done.

## Autonomy and escalation

Continue through routine implementation, testing, diagnosis, and safe remediation
without asking the product owner to manually regress the feature. Escalate only
for materially ambiguous behavior, external credentials/MFA/vendor approval,
irreversible actions, or a failure that remains unsafe after root-cause work.

Do not interpret “autonomous” as permission to merge, deploy, change production,
weaken authentication, mutate customer data, or delete work outside the authority
given for the task.

## Board updates

Update `docs/PROJECT_BOARD.md` at intake, owner handoff, contract approval, gate
failure/pass, merge, release, and blocker changes. Prefer links/IDs and concise
evidence over narrative. Never erase useful history merely to make the board tidy.

If external Linear access is connected, mirror the board after first reconciling
IDs and statuses. The repository board remains authoritative until that mapping is
verified and documented.

## Completion response

Report the outcome, current board state, owner, verification evidence, and any
decision genuinely required from the product owner. Do not call an item complete
while hiding a failed test, missing runtime check, uncreated PR, or external gate.
