# DB-139 Ready to Close ownership verification

Status: Done — PR590 merged, exact revision deployed and signed-in production acceptance complete. Historical checkpoints below are superseded by the final release acceptance section.
Owner: Backend & Integrations. Branch codex/ets-ready-close-ownership, based on released main c66cabf230e54370fdcfeb083b9b767148ee00ca. Separate completed-footer checkout reused cleanly; held B1/importer checkouts untouched.

Architecture approved the bounded shared predicate in contracts/db139-ready-close-ownership.md. Actual SQLite tests cover all three query paths, ETS and linked historical provenance, cancelled/deleted invoices, foreign-tenant veto negatives, >50 history/native pagination, counts/value agreement, native zero/null source, pending-Zelle routing, explicit source loading and history reachability. New ownership tests2 plus adjacent regression29 passed. Independent QA reproduced26 backend and17 frontend checks and independently compiled PostgreSQL correlation/order/limit SQL. Source/test and targeted tenant/source security GO; no financial, status, migration, provider or collector changes.

Frontend component checks17 passed, including legacy and new imported completed/invoiced fallbacks before native/Zelle instructions. Actual Night component rendering exposed hardcoded dark status ink; the existing Night/high-contrast selector now includes status strong, independently reviewed. Light remains unchanged.

Local runtime preflight: intended clean branch/base above; frontend127.0.0.1:5173 PID22155 and backend127.0.0.1:8000 PID22116 initially served this checkout. Approved shared env symlinks, backend URL explicitly overridden to localhost truckpitstop_db135, schema179 and0invoices verified; no migration/reseed. Backend restarted after source edits as PID23550; listener cwd matches this backend, readiness200 database/RedisOK and served OpenAPI contains nullable RecentOrder.source. Frontend auth/me proxy returns401 as expected without a synthetic login; no claim of full signed-in local workflow. Vite proxy explicitly8000, runtime branch/SHA configured. Actual temporary synthetic component harness showed ETS history with no native instruction, native Invoice Customer unchanged, Light/Night desktop1280 andmobile390 fit without horizontal overflow. Night text rgb246,248,251 after correction. Harness removed. This is component/browser evidence, not authenticated full-application or production acceptance.

Private read-only fixed-cohort baseline captured at sole184:47 invoices/15 settlements/33 payments/10 ledger events/0 overpayments/0 credits, transaction_read_only on.

TypeScript and production build passed; changed-source ESLint and diff checks passed. Temporary harness unused-import failure was removed before the clean full build.

Historical pre-release checkpoint (superseded by final acceptance below): sharedCI-slot release, focusedPR/protectedCI, normalmerge/deployment, actual signed-in production Light/Night desktop/mobile queue+history and fixed financial retention were pending. Do not mark Done before these gates. Standard native SENT/recorded-zero-remaining mismatch remains tracked separately without financial repair.

## Recurring frontend CI diagnosis — Release & Reliability

The user assigned this release chat to fix the recurring test failures and land
PR590. Baseline head1d489796 retains the independently reviewed product source.
The same four failed suites reproduced under CI-like three-worker execution:
18 failed /134 passed in125.68s. With one worker and unchanged tests, defaults,
fixtures and assertions, all152 passed in118.00s. Price-builder time dropped
from the contended failure run to47.8s. Across590/586/589, failures moved between
unrelated interaction tests at default async/test deadlines. This demonstrates
worker contention in the functional test harness; high host Chrome CPU is an
additional observed load, not an established sole cause.

The minimal correction caps Vitest to one worker when CI is set. The separate
GitHub jobs remain parallel; every test, assertion, default deadline, retry
policy, protected context and disposable-worker boundary is preserved. This
changes test execution scheduling only, not the application bundle or API.
Independent infrastructure QA gives source/evidence GO, conditional on the full
protected PR suite. A redundant local full run was stopped after user steering
to avoid duplicating GitHub integration work; partial progress is not a full
pass. The152-test before/after comparison is the local regression evidence; the
complete1,990-test protected CI step is the final integration gate. No blind
retry of the old failed job was requested.

Fresh local preflight: this checkout is codex/ets-ready-close-ownership at1d489796,
initially clean, with no5173/8000 listener. The existing .env identifies
localhost/truckpitstop and was preserved. This test-harness-only correction does
not start, migrate or reseed that populated database. No new local application
visibility claim; actual signed-in production acceptance follows deployment.

### Gate return and second confirmed cause

Candidate301c5831 critical CI passed209/210 with no deadline failures. Its single
failure at PriceBuilderPanel.pending-feedback.test.tsx:765 was different: the
async findByRole lookup returned a button which the subsequent assertion found
detached. The250ms debounced inventory query can replace the picker in that
microtask gap. The assertion now re-queries and checks the exact same role/name
inside one synchronous waitFor callback; the original1s bound and all creation,
cancellation and clear assertions remain. Both focused main/operation cases
pass2/2. Independent test QA GO is conditional on consolidated exact-head CI.
No test/job retry, timeout increase, application or financial change is added.
The affected creation, skeleton and insufficient-stock cases now also wait for
the exact final inventory-typeahead query to reach success/idle, so visible
intermediate results cannot satisfy final-search readiness. Each render owns a
fresh QueryClient. All four focused affected cases pass4/4 in15.21s; independent
QA reviewed this synchronization and retained stock-override/payload assertions.
Candidate301c5831 full frontend job118416053856 and its actual Run full frontend
suite step both completed success in run39357582299. This certifies the worker
cap at that head; the consolidated test correction still requires fresh exact-
head protected CI. No second local full suite is run.


### Focused pricing interaction cases

Candidatebdbb6e5d critical CI passed209/210. The corrected picker cases passed;
a different pricing-segment case hit the whole-test5000ms deadline. Its six
pointer/click sequences tested label selection, direct radio selection and
press/release focus in one case. Local step profiling completed the original
case in2308ms, including1567ms cold render; this demonstrates setup cost and
provides no evidence of a failing product assertion. Split those independent
input paths into three focused cases, preserving every original assertion and
real userEvent pointer-event checks. No timeout, retry or application change.
All seven selected pricing/picker cases pass in24.33s total; the slowest label
case is3376ms. Fresh independent QA (not the participating investigator) reviewed
assertion parity and gives source GO; exact corrected-head protected CI and
production acceptance remain required. The two additional cases bring the full
frontend inventory to1992 tests. No duplicate local full suite is run.


### Single-pass CI gate return

Run39359777590 atbdbb6e5d is not a passing release: critical209/210 failed one
whole-test deadline; full1981/1990 failed9 across5 files in1203.73s, versus prior
301c5831 full1990/1990 in637.23s. Playwright exhausted its15-minute job budget
during dependencies/database setup and cancelled27s after smoke startup.
These results cannot certify the feature. No unchanged run was retried.

User broadened DB-CI-001 to remove duplicate local/GitHub cycles and pipeline
waste. Critical lists are preserved in a shared manifest; remaining jobs exclude
exactly those files. Actual collection verifies frontend17+174=191 and backend
33+265=298 with no overlap. Missing/duplicate/unsafe/glob-zero guards pass
(5 Python and1 Node checks), and actionlint/diff checks pass. Legacy informational
contexts now propagate failures. Critical jobs gate their expensive dependents;
trusted scope/no-op behavior and disposable-worker isolation are retained.
Smoke now has25 minutes total setup budget and5 minutes for actual smoke;
Playwright assertion/webserver deadlines stay unchanged. Architecture and fresh
independent QA/Security source GO; corrected exact-head CI remains required.
No local full test execution or production application change is added.

The nine failures from bdbb6e5d full CI all pass unchanged in a focused local
CI-mode run:9/9 across5files,40.42s. No blanket test rewrite or assertion/deadline
change is justified by that result. Host resource contention is observed; the
new scheduling/partition correction still requires actual exact-head CI proof.


## Final release acceptance — 2026-10-20

Status: Done for DB-CI-001 single-pass CI and DB-139 Ready to Close ownership.
Accountable release owner: Release & Reliability; product source owner: Backend & Integrations.

- PR590 normal squash merge76966f2490c4057586c7f2228387e8d36955f71a. Exact checked head5598ce3929d9e977cbdca88321d3a05df29a933a and PR merge-ref8b716eaea3e36078f5a7e1dd52c2bbea18543e33 have tree239174fe4b594e8e9baa79008b66dedc55d89700, identical to the merged tree.
- Protected run39362785304: all six jobs success and no failed steps. Frontend212critical +1780remaining =1992 passed across191files; execution46.79s +322.14s. Backend584critical +3375remaining =3959passed,314 existing skips; remaining1293.81s. Playwright5passed in17.4s. Partition guards verify17+174frontend and33+265backend files, disjoint and complete. Architecture plus fresh independent QA/Security source GO.
- Duplicate main run39366109848 cancelled only after checked/merged tree identity and complete PR success; no gate bypass or unchanged failed-job retry.
- Railway Web594f8e9f-ba92-4c65-b8e7-0e64c812b369 andWorker3596e152-5f39-4a5c-964f-5a7bd39b8749 SUCCESS on exactmerge. Served /build-version reports exactmerge; /health/ready reports production ready, database and Redis OK. The public static build-version.json URL is an SPA fallback and is not used as version proof; the documented build-version endpoint reads the emitted frontend stamp.
- Actual signed-in NC acceptance:1280x900 desktop and390x844 mobile, Day and unsaved Night preview. Ready to Close contains native orders only; daily-workset rows, pagination and lane value/count agree. The previously queued ETS example remains searchable in Repair Orders and opens with its source-backed total and Paid in ETS status, with no native billing action. No horizontal document overflow at either tested width; status text readable. Appearance previews discarded, saved Day restored and viewport overrides cleared.
-146 captured normal acceptance request events, no truncation, zero POST/PUT/PATCH/DELETE API writes, zero appearance or financial writes. Fixed approved financial cohort matches pre-release byte hashes in every table, with sole schema184 retained. Private records, hashes, values and screenshots remain outside Git.
- The held importer/collector work and separately tracked native SENT/zero-remaining inconsistency are outside this queue correction. No financial repair, provider send, invoice creation or collector setting change was performed.
