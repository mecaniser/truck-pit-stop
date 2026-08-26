---
name: dieselbridge-delivery-team
description: Govern DieselBridge delivery with risk-proportional routing, verification, and release evidence. Use for DieselBridge product work, defects, coordination, QA, releases, or board updates; keep low-risk UI work on the fast lane and reserve independent specialist gates for changes that justify them.
---

# DieselBridge Delivery Team

Route every request through one accountable delivery path and keep
`docs/PROJECT_BOARD.md` synchronized with repository and runtime evidence.

Read `AGENTS.md`, `docs/DELIVERY_TEAM.md`, and `docs/PROJECT_BOARD.md` before
acting. Read `references/handoff-contract.md` when handing work between roles.

## Choose the lightest safe lane

Classify the work before routing it. Do not promote a lower-risk item merely
because the repository has specialist roles available.

- **Fast UI lane:** an existing authenticated surface, using existing API and
  permission contracts, with no auth, tenant, data-model, migration, payment,
  dependency, worker, infrastructure, or feature-flag change. Use one
  accountable frontend owner, a concise board entry, focused component tests,
  changed-source lint, and one signed-in browser pass that covers the changed
  desktop interaction plus the relevant compact/mobile state. Protected PR CI
  is the integration gate. A separate Architecture, Security, QA, Release, or
  extended canary task is not required unless evidence exposes broader risk.
- **Standard product lane:** a meaningful workflow or cross-layer behavior
  change without a sensitive boundary. Add Architecture only for a new or
  changed contract and add independent QA for the affected journey.
- **High-risk lane:** auth, tenant isolation, secrets, payments, sensitive data,
  migrations, destructive operations, workers, infrastructure, or a risky
  rollout. Use the full contract, independent Security/QA, rollback, and canary
  path.

When uncertain, inspect the actual diff and contracts first. Escalate the lane
only for concrete risk, not ceremony.

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
5. **Gate.** Apply the selected lane. Fast UI work uses owner evidence plus
   protected PR CI; do not manufacture a separate QA handoff. Standard work uses
   independent QA for the changed journey. High-risk work also uses independent
   Security where applicable. A gatekeeper must not have implemented or directed
   the change. A gate failure returns to the responsible owner with reproduction
   evidence.
6. **Release.** Match release proof to risk. Fast UI work needs successful
   deployment plus one route/browser smoke check; do not add a timed canary,
   repeated health loops, worker inspection, or unrelated service checks.
   Standard work verifies the changed runtime journey and relevant service
   health. High-risk work records rollback signals and post-deploy observation.
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

For the Fast UI lane, update `docs/PROJECT_BOARD.md` at intake and completion,
plus any real blocker or failure; do not narrate every internal step. Standard and
high-risk lanes also record meaningful handoffs, contract approval, independent
gates, merge, and release. Prefer links/IDs and concise evidence over narrative.
Never erase useful history merely to make the board tidy.

If external Linear access is connected, mirror the board after first reconciling
IDs and statuses. The repository board remains authoritative until that mapping is
verified and documented.

## Completion response

Report the outcome, current board state, owner, verification evidence, and any
decision genuinely required from the product owner. Do not call an item complete
while hiding a failed test, missing runtime check, uncreated PR, or external gate.
