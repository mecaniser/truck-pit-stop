# DB-048 payment-panel QA correction

Owner: root Frontend. Date: 2026-09-11. Baseline: deployed PR381 merge `8b8901813c79b1cd034f6d4d018cd2c356d872fa`. Branch: `codex/db048-payment-panel-qa`.

## Acceptance and boundaries

- Explicit partial amounts and partial mode survive same-invoice charge/version refresh. Only full-balance mode follows balance changes automatically.
- Invalid or newly excessive drafts stay editable, cannot submit, and are not clamped or reinterpreted. Inclusive limits are $0.01 through the available balance.
- Quote and creation payload use the same principal/version. Stale, failed and refreshing quotes block collection.
- Tender evidence never migrates to another tender/provider/invoice. Cash remains full-invoice only; returning to noncash restores the partial draft.
- Freeze request inputs while creating/confirming. Late responses may invalidate cached settlement data but cannot update another invoice's open panel.
- Preserve existing pending Zelle evidence, Fleet immutability, admitted tender choices and history locks.
- No backend/API/schema/worker/payment-policy change, provider operation, invoice adjustment, cash receipt, export release or historical-record mutation in production.

## Findings and fixes

| Finding | Result / source commit |
|---|---|
| Partial amount reset to full after fee save | Fixed `c14272ad`: explicit draft independent of settlement version |
| Terse numeric-range error | Fixed `73b31197`: “Enter at least $0.01 and no more than [available], the amount available to pay.” |
| Negative amount silently became positive | Fixed `ae59342d`: retain raw input and block invalid quotes/submission |
| Check evidence reused by Zelle; invoice-A drafts reused by invoice B | Fixed `6376a840`: isolate tender/provider evidence and key invoice context |
| Editing during preparation changed confirmation evidence | Fixed `3f790f82`: freeze payment controls during requests |
| Late invoice-A response replaced invoice B | Fixed `7ca511bb`: ignore unmounted panel callbacks while invalidating settlement caches |
| Existing pending-receipt review had the same negative-input/pending/late-callback issues | Fixed `7abda795`: equivalent safeguards in pending review |

22 new regressions committed in `edb61bdab7bd4dfc1ac69cb09dd15e36df3085e8`; existing tests unchanged.

## Verification

- Owner: all10 payment test files, **105/105 passed**. Covers settlement UI, cash, charge edits/layout, tax exemption, Fleet, pending Zelle, provider API selection and22 new draft/race cases.
- Independent QA/Security: **GO at edb61bda, 57/57 passed**, no unresolved P0/P1/P2. Earlier independent checks reproduced pending-input and late-response bugs before their fixes.
- TypeScript, changed-source ESLint, production build and diff whitespace check pass. An initial test invocation from repository root lacked the frontend configuration; rerun from `frontend` is the authoritative result.
- Browser: actual React components with isolated Axios fixtures at `http://127.0.0.1:5196/journey-preview.html`, not a static mockup. Payment/provider submissions blocked by the preview adapter.
- Frame-sampled18 saves (supplies/tax/card fee off/on at1280,390,320px;250ms simulated request delay): explicit500.00 retained, rows/input stayed mounted, **zero modal-height shift and zero horizontal overflow**.
- Rendered checks: excessive6000 and negative-50 stay invalid; invalid quote totals show a dash and cannot collect; Check reference/note clear on Zelle; Cash is full1160.49 with no partial input and returning to card restores500.00; all six admitted tenders available through inline More; arrow-key selection/focus and dialog close/reopen work.
- Existing pending-Zelle fixture retains submitted reference/note; charge switches stay locked while a receipt is pending. Negative received amount remains negative with confirmation disabled.
- In-app preview tab8 verified live. Production tabs are at staff login: authenticated production visual acceptance requires sign-in and is not claimed by local tests.

Local evidence is retained in `.gstack/qa-reports/`: before/after screenshots, `geometry-1280.json`, `geometry-390.json`, `geometry-320.json`, and the sampling script. No new application console exceptions during changed-flow checks; old Vite connection-refused messages were from the intentional preview-server restart.

## Release

Focused frontend-only PR and normal protected CI/merge. API/UI deployment only; no migration or worker rollout is required. Rollback is the prior API/UI deployment. PR, merge, exact deployed SHA/readiness and acceptance status will be recorded here and on the board after release.
