# PR760 Settings history + Fleet permission display — current-main review

**Local regression and documented runtime acceptance pass; publication is paused for parent review.** Frontend & UX accountable. No push, ready-state change, formal GitHub approval, remote merge, deployment or production change. #748 Security NO-GO and all other explicit holds/denials/approvals remain intact.

## Exact source and ownership

Read-only remote checks before preparation and after acceptance returned:

- Main **1d57758d887ddbd26e1d4660a58573c653b61f6d**.
- PR760 **66818d29376a0f7d27cda77ea34e77e74dbb2a73**, branch codex/settings-section-history; GitHub metadata open/unmerged/draft=false/mergeable=false. That metadata is not release approval and was not changed.
- Original owner checkout `/Users/sergio_m1_promax/.codex/worktrees/settings-section-history/truck-pit-stop` clean at the PR head. This is repository evidence, **not proof the owner is idle**. Supported task-list/read methods were not exposed in available tools and codex CLI was not installed. The denied Codex UI and hidden session files were not used. Parent must resolve active ownership/coordination through an authorized route before publication.
- Prior prepared combined candidate `/tmp/dbn-pr760-fleet-combined-20261103` remains clean at21d8e4b55bb66a0fa1124f184b20ac74d15ac5b2. Original PR760 integration3e11bfe2 and standalone Fleet correctionddc09bb1 also preserved.

New isolated worktree `/tmp/dbn-pr760-fleet-current-main-20261104`, branch `codex/pr760-fleet-current-main-20261104`. **Tested application commit63780dd292f41b2a037510dc7d8dc6c76d085d35** from verified main1d57758d. Frontend tree **bf7e230e024e2dd3768e5cbfaa3cdd2662220dce**; backend tree **27e0cef3fa5457829fa5f5fcb5a5f2b807760ce8**, exactly current-main backend.

Only two application/test files differ from main: `UnifiedSettingsPage.tsx` and its test. Their Git blobs exactly equal the prior combined21d8e4b5 candidate. Applied the prepared source-only delta onto current main cleanly; no application conflict/corrective edit was needed. Main's newer booking, payment, Shop Work, health and telemetry changes remain intact. No #748 application source was imported. Main's board history is retained and the two original PR760 owner intake/review paragraphs are preserved as historical records. [Composition proof](pr760-current-main-20261104/source-composition.json).

Behavior: URL-authoritative authorized Settings selection survives reload/Back/Forward, including compact picker and existing Fleet/Fees/provider-return paths. Fleet uses the existing taxes_fees gate for configuration/companies reads, distinguishes pending/error/403 from empty data, offers Retry and suppresses unusable unlock. Existing backend permission/tenant contracts and editing/Save behavior are unchanged.

## Automated gates

- **Full frontend2797/2797,249files,397.21s PASS.** Expected error-boundary/jsdom diagnostics remain in raw output; no failed tests.
- **Build/typecheck/shared-control guard PASS**; changed-source lint against1d57758d: zero new violations across2files; diff/source checks pass. Lockfiles/dependencies unchanged; copied matching installed dependencies into this isolated worktree.
- **Relevant backend32/32 PASS**,22warnings: internal Fleet pricing/authority, Fleet board and Fleet manager access. Current backend source mounted read-only into existing test image `portal-booking-backend-tests:136b96d5-node22`, networking disabled, in-memory fixtures. Runtime image lacked pytest; an existing test image resolved that test-environment gap. No test dependencies installed into shared services.
- Fresh independent Security: scoped GO63780dd2,42Settings +14adversarial probes including revoked grants, protected callbacks, cached/late data and actual SessionQueryProvider tenant replacement. No application edits.
- Fresh independent QA: scoped GO63780dd2,42Settings +19external navigation/permission/read-state probes; separate runtime evidence audit GO. The audit recomputed six DB equalities, inspected10screenshots and reviewed redacted normal-login/unlock/Save transcripts, full runtime stamp and source mount. It audited owner-executed acceptance rather than independently replaying browsers.

Backend source/contracts do not change in this candidate; a full backend suite was not rerun. The32 relevant tests plus actual current-backend HTTP/SQL acceptance cover the affected API use. Hosted exact-publication-head CI remains required; no local result substitutes for it. [Logs and independent reports](pr760-current-main-20261104/).

## Disposable native runtime

Owned project `pr760-current-main-qa-20261104`: PostgreSQL15 tmpfs, Redis7, current backend read-only mount, isolated API network and credential-free localhost8284 gateway; no worker/provider credentials. Alembic **201_customer_payment_profiles (head)**. Vite5284 from this worktree rendered full title `codex/pr760-fleet-current-main-20261104@63780dd292f41b2a037510dc7d8dc6c76d085d35`; process/cwd match; proxied readiness200 with database/RedisOK. [Identity](pr760-current-main-20261104/runtime-identity.json), [mount/schema/images](pr760-current-main-20261104/).

Guarded seed creates one synthetic shop, owner, restricted admin, taxes_fees-granted admin and two Fleet authorities. All three roles use normal email/password login in separate named browser sessions. No auth-state injection or API-response-data mock. Only the Fleet GET fault test delays/aborts transport; Retry fetches real backend data. No copied .env/shared database/existing secret file. Generated passwords/SECRET_KEY are redacted from retained transcripts/config; raw credential-bearing runtime files are discarded.

Baseline: Original Current Main QA Fleet / Performance Fleet; rates7.25sales,4.5supplies,2.25service,145labor,65internal. Synthetic counts3customers,1repair,0invoices/payments/invoice-attempts/counter-sale-attempts.

## Browser/HTTP/SQL acceptance

All roles passed actual desktop1440x1000 and phone390x844 Security/Appearance selection, reload, Back/Forward, picker Escape and no horizontal overflow. Owner and restricted admin passed Manage on Fleet board -> return to exact Fleet Settings URL at both widths. Overview was genuinely empty in this fixture; populated board behavior is covered by backend/component suites, not claimed from these screenshots.

| Case | Result |
|---|---|
| Owner desktop Save | Password unlock; name Owner Current Main Saved Fleet and alternate authority; real PUT200, reload retains both, independent SQL matches. |
| Granted-admin phone Save | Unlock; name Admin Mobile Current Saved Fleet and Performance Fleet authority; real PUT200, reload and SQL persistence, no overflow. |
| Restricted desktop/phone | Access explanation, Overview/board still available, no false Not set or Unlock. Six denied links/callbacks show Profile; zero protected configuration/company/Stripe/QBO GETs. |
| Restricted validly-shaped authenticated PUT | Real403; attempted name/rates/default authority do not persist. SQL snapshot exactly equals the last authorized mobile Save. |
| Already-unlocked phone admin then grant revoked in synthetic DB | Existing visible Save returns403 with visible permission error. No targeted setting/rate/count changes. Dirty editor remains until reload; reload shows restricted explanation. This pre-existing behavior is disclosed, not called an immediate editor dismissal. |
| Owner phone read failure injection | Delayed real GET shows Loading with zero false Not set. Two aborted GETs reach truthful error; Retry makes real200 and restores actual values. |
| Owner local callback/alias routing | Fees shows Payments and survives reload; Stripe return/refresh and QuickBooks connected queries clean up to section=payments and survive reload. No provider OAuth exchange. |
| Owner restoration | Actual PUT200 of original Fleet name/default authority; reload and independent SQL exactly match original baseline. |

Both authorized saves preserved all five tax/labor rates. All denial snapshots equal the authorized snapshot; final restored settings and six business-table counts exactly equal baseline. These are representative role/width Save combinations (owner desktop/admin phone), not every possible combination. Count snapshots are not a full-row diff. [Browser results](pr760-current-main-20261104/browser-results.json), [DB assertions/snapshots](pr760-current-main-20261104/database-assertions.json), screenshots and redacted interaction transcripts retained alongside.

The initial history harness incorrectly waited for a Security heading instead of the actual Password Management text; fixed locator only. The initial delay handler cleanup raced an already-handled route; corrected transport harness cleanup after completion. No application edit was needed. Independent external harness setup/toast-mock corrections are recorded in their reports. Actual WorkOS/provider flows, production data and long-running multi-tab financial workflows were not exercised or changed. No claim of zero HTTP warnings is made; existing Appearance migration warnings are outside this source delta.

## Cleanup and remaining publication gates

Original fixture settings were restored through actual UI and SQL-verified, then all three owned browsers, Vite5284, owned API/gateway/Redis/PostgreSQL/network and tmpfs data were stopped/discarded. Generated credentials/raw CLI logs/runtime directory and owned Playwright artifacts are removed after sanitized evidence capture. Other worktrees/runtimes remain untouched.

Remaining requirements before publication/release:

1. Parent reviews this concrete source/evidence. No push/mark-ready/merge/deploy before that review.
2. Confirm active owner coordination by an available authorized task route. Clean owner checkout alone is insufficient.
3. Decide publication shape: current PR760 contains history only; the local candidate also includes the prepared Fleet display correction. Parent may update scope/description or retain separate focused PRs using the preserved standalone branches. No remote decision was made here.
4. Reverify then-current main/head and run required exact-published-head CI/release checks. No GitHub approval or production acceptance is claimed.

Local measured acceptance and scoped independent gates pass. This does not clear #748's Security NO-GO or any other explicit hold/denial/required approval. Not Done or released.
