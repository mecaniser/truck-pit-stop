# TruckPitStop — Claude Code context

This repository's rules already exist in two places that Claude Code does not
load automatically. Read them; this file does not restate them, so that they
have exactly one source of truth.

## Read these first

| File | What it governs | When |
|---|---|---|
| `.cursor/rules/tdd.md` | **Iron Law: no production code without a failing test first.** RED-GREEN-REFACTOR. | Before writing any production code |
| `.cursor/rules/testing-stack.md` | Runners, fixtures, mocking, file locations, naming for backend/frontend/e2e | Before writing any test |
| `AGENTS.md` | Delivery governance: owners, lanes, gates, definition of done | Before starting an item |
| `docs/DELIVERY_TEAM.md` | Risk lanes (Fast UI / Standard / High risk) and required evidence per lane | At intake, to pick the lane |
| `docs/PROJECT_BOARD.md` | The live board; every task needs an item here | At intake and each handoff |

A change that adds or alters an API field, response shape, or enum value is
**not** Fast UI — it is a contract change, and `AGENTS.md` rule 3 routes
contracts to Architecture before frontend and backend work proceed in parallel.

Direct pushes to `main` are prohibited (`AGENTS.md` rule 9): one short-lived
branch and one focused PR per releasable outcome. `main` also enforces linear
history, so PRs are squash-merged.

## Environment

- Backend tests run on the repo venv, not system Python:
  `cd backend && ./venv/bin/python -m pytest` (system `python3.11` has no pytest).
- Do not export `DATABASE_URL` when running tests; the suite uses in-memory
  SQLite and the env var redirects it at real Postgres.
- Frontend: `cd frontend && npx vitest run <path>` for a focused suite,
  `npx tsc --noEmit -p tsconfig.json` to typecheck.

## Money and inventory conventions

- `decimal_money` lives in `app/services/parts_operations_service.py` — there is
  no `app/core/money` module.
- Inventory value is `(cost + core_charge) x stock_quantity` — the core deposit
  is included, so the figure matches the Analytics dashboard and the Easy Truck
  Shop "Total Value" column. See `app/api/v1/endpoints/reports.py`.
- Totals over the catalog exclude retired (`ets_retired_at`) and placeholder
  (`is_placeholder`) parts, matching the tracked/needs-reorder counts.
- `Inventory.selling_price` is NOT NULL — test fixtures must set it.

## Verification

`AGENTS.md`: "Code, tests, migrations, pull requests, and deployed behavior are
evidence. A conversation summary alone is not evidence that work is complete."
A passing test you wrote after the code is not evidence it would have caught the
bug. Confirm a new test fails without the change before trusting it.
