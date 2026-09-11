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

### Merge receipt

[PR382](https://github.com/mecaniser/truck-pit-stop/pull/382) merged at2026-09-11 18:31:14UTC as `d3ef19d50690f3926b6bcc038a96c58f25594009`. Merge tree `62c0970faace067e0ab72d114d0353b0fea4726d` equals branch26b3a86f; only evidence documentation differs from independently approved edb61bda. All six protected checks passed in run34632797363: frontend619/619, backend1850 passed/73 skipped, Playwright5/5, critical suites, migration/configuration check. Deployment verification follows; authenticated production acceptance is still blocked by staff login.

### Deployment receipt

Verified2026-09-11 18:34UTC: API/UI deployment `c87f83b1-525f-4b78-9295-618ffe2bceed` SUCCESS at merge `d3ef19d50690f3926b6bcc038a96c58f25594009`. Production serves `index-QzgxEglg.js` and its `SettlementResolutionPanel-Cdyn_tA7.js` contains the new inclusive amount-limit message. `/health/ready` is healthy with database/Redis OK and new-instance uptime34s then75s. Worker remains `27b65959-2379-48e3-a53b-32a9ea64885e` at50421e00; no worker/migration/activation/export action performed. Startup log contains no application startup error. Correct settlement endpoint rejects unauthenticated access with401 (an initial incorrectly composed URL returned404 and was corrected; not a product defect).

Released code, not fully authenticated runtime acceptance: the in-app production session remains signed out. User was asked to sign into DieselBridge only, not QuickBooks, for a read-only walkthrough. No financial mutation will be used for acceptance. Local in-app preview5196 remains open and serves the final candidate. This post-merge receipt is retained locally and posted durably on PR382; the merged committed report contains pre-release verification.
