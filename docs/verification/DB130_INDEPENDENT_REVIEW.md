# DB-130 independent review — 2026-10-15

Reviewer: independent QA Gatekeeper (`outside_search_qa`), with no implementation
or contract participation. Scope: the working diff on
`codex/outside-history-search` against the approved DB-130 contract.

## Decision

**PASS for source and automated journey review. No blocking findings.** This is
not a production or visual acceptance claim. The delivery owner must complete
the actual Light/Night desktop/mobile browser checks, protected CI, and deployed
version/health checks before marking DB-130 Done.

## Evidence independently checked

- Backend: `python -m pytest tests/test_external_service.py -q` — **46 passed**.
  This includes full-set provider/work/reference search beyond page one,
  trimming and mixed case, literal wildcard/backslash/SQL-looking text,
  no-match/blank behavior, 200/201 bounds, stable tied ordering, filtered counts,
  voided/deleted/exact-vehicle/tenant scope, role denial, HTTP shape/no-store,
  existing mutation and history invariants, and no new financial side effects.
- Frontend: Vitest for `ExternalServiceHistory.test.tsx` and
  `ExternalServiceReceipts.test.tsx` — **91 passed (36 + 55)**. New cases exercise
  debounced search and a delayed prior response, page reset, clear and focus,
  retry versus no matches, editor filter locks, Cancel/Escape, a draft whose
  conflicting remote edit removes it from matches, post-save invalidation and
  page recovery, identity reset, and Show voided.
- `git diff --check` — passed.
- PostgreSQL dialect compilation of the exact `icontains(..., autoescape=True)`
  form confirms bound parameters and `ILIKE ... ESCAPE '/'`; `%` and `_` are
  escaped as literals. The focused database tests use SQLite; this compilation
  check does not claim a PostgreSQL integration run.

## Review conclusions

The existing vehicle/role/tenant gate still runs before list reads. The new OR
predicate is added to the same conditions used by count and paginated select;
it does not weaken any ownership, deleted, or voided predicate. No mutation,
schema, receipt access, or auth contract changed.

The normalized query is part of the scoped cache key and request. Pending input
hides old results; a late response cannot replace the new query's rows. Search,
clear, and voided controls are locked while editing. Failed refresh does not
present cached rows as current results, and a filtered-out conflict retains the
draft with explicit recovery/cancel. Successful saves invalidate all searches
for the vehicle and return to page one with the query retained.

The CSS uses existing theme tokens, wrapping whole controls, a bounded input,
visible focus, and mobile/coarse-pointer minimum sizes. These source checks and
DOM tests do not establish rendered contrast, no overflow, scroll behavior, or
physical touch-device usability. Actual desktop, 320/390 portrait, compact
landscape, Light/Night, and customer/repair-order return checks remain with the
delivery owner; production fixtures must remain synthetic and be restored.

Pre-existing deprecation and Browserslist-age warnings were emitted; no test
failures or new dependency changes were observed.

## Local visual gate

**PASS for the six supplied local captures; no blocking visual findings.** The
reviewer independently opened these images with `view_image`:

| Capture in `/tmp/db130-qa/` | Dimensions | Result |
| --- | --- | --- |
| `local-light-desktop.png` | 1280 × 720 | Dense desktop search, count, result and controls readable |
| `local-light-320.png` | 320 × 700 | Whole controls wrap; search and result fit narrow portrait |
| `local-light-landscape.png` | 740 × 400 | Search and record remain usable between compact header/footer |
| `local-night-mobile-empty.png` | 390 × 700 | Distinct zero-match state; query, clear and voided controls readable |
| `local-night-320.png` | 320 × 700 | Query/result readable; no visible horizontal clipping |
| `local-night-landscape.png` | 740 × 400 | Theme-consistent search and record with visible focus |

The scoped search surface shows readable foreground/background contrast, a
visible focus outline, and no wrapped button labels or visible horizontal
overflow. Search/clear/voided controls remain distinct from the native history.
No Night desktop capture was supplied for this review, and no pixel contrast
ratio or physical-device certification is asserted.

The delivery owner separately reports real local ref/provider/work searches,
clear/no-match, typing, Cancel/Escape retaining the query, disabled filters while
editing, and customer Back followed by return to originating `#PERF-0000001`.
Those interaction results are owner evidence, not actions performed by this
reviewer. Production browser checks, protected CI and release identity remain
required. All narrow-screen captures use simulated browser viewports.
