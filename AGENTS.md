# DieselBridge Agent Constitution

All product work in this repository follows the DieselBridge delivery team workflow.
Use `.agents/skills/dieselbridge-delivery-team/SKILL.md` for intake, routing,
implementation, verification, and release work.

## Source of truth

- `docs/PROJECT_BOARD.md` is the current delivery board.
- `docs/DELIVERY_TEAM.md` defines ownership, handoffs, and escalation rules.
- Code, tests, migrations, pull requests, and deployed behavior are evidence.
  A conversation summary alone is not evidence that work is complete.

## Non-negotiable rules

1. Give every implementation task one accountable owner and one board item.
2. Define acceptance criteria before editing code. Include negative and tenant-
   isolation cases when applicable.
3. Assign API and data contracts to Architecture & API Contracts before parallel
   frontend/backend work begins.
4. Do not let the implementing owner approve its own QA or security gate.
5. Do not mark work Done until implementation, automated checks, runtime
   acceptance, PR/merge state, and release evidence required by the item exist.
6. When a gate fails, return the item to the owner with reproduction evidence;
   do not ask the product owner to perform routine regression testing.
7. Escalate to the product owner only for ambiguous product intent, irreversible
   or high-risk actions, external credentials/approvals, or failures that cannot
   be safely resolved after investigation.
8. Preserve unrelated and uncommitted work. Never clean a dirty worktree by
   deleting or overwriting changes of unknown ownership.
9. Use one short-lived branch and one focused pull request per independently
   releasable outcome. Direct pushes to `main` are prohibited.
10. Update the board at intake, handoff, gate failure, merge, and release.

## Definition of done

An item is Done only when its acceptance criteria are met and the board records:

- accountable owner;
- relevant contract or migration impact;
- focused automated test results;
- Playwright/runtime evidence for changed user journeys, or an explicit reason
  why runtime testing does not apply;
- security review for auth, tenant boundaries, secrets, payments, or sensitive
  data changes;
- branch, pull request, and merge/deploy evidence as applicable;
- no unresolved blocker or required follow-up hidden in the completion note.
