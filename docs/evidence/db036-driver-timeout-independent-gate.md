# DB-036 driver timeout recovery: independent QA and Security

Reviewed October 16, 2026 by `independent_speed_gate`, with no implementation
participation. Backend & Integrations remains accountable. The reviewer changed
only this evidence document and performed no production or browser actions.

**Candidate QA: GO. Security: GO.** No implementation finding remains at
`adc02f07aa280cf8f6bf8740881a6e3cd3e86c6c`, based on `7299722d`.
The contract is [driver identity timeout recovery](../contracts/db036-driver-timeout-retry.md).
The SHA-256 of the binary diff for `collect.cjs` and `collect.test.cjs` against
that base is `b4c1ade444d4dcbe456316019c25ad23c9838774bd1109d9e0adb40491700d7a`.

Independent checks passed:

- All 36 tests in `backend/scripts/motive_drivers/collect.test.cjs`.
- Node syntax validation and `git diff --check` against the review base.
- An additional in-memory exhaustive matrix of 686 cases: initial or known VIN,
  with all three-attempt combinations of null, timeout, matching VIN, different
  VIN, changed source, ambiguity and other reader error. The matrix checks exact
  read counts, immediate terminal outcomes, retained exception identity, bounded
  retry diagnostics and omission of raw exception content.

The helper shares one three-read budget between nulls and TimeoutErrors. Each
read still invokes the unchanged fresh-document reader, including exact route
validation and page cleanup. A matching verified VIN can recover; after any
timeout, exhaustion without a VIN rethrows the timeout even if subsequent reads
were null. Three genuine null reads retain the previous semantics. A non-null
mismatch or non-timeout reader error aborts immediately, including after an
earlier timeout. No fourth read is possible.

Caller review confirms the safe `ui_timeout` diagnostic remains bounded and
excludes VINs, raw page content and exception text. Exhausted verification still
prevents a complete collection. The patch does not change directory/account/
assignment verification, tenant/import boundaries, journals, schedules, storage,
public APIs or the location collector.

This is candidate approval, not deployment approval. After the planned rebase,
verify that the two reviewed collector files retain the same application change,
pass protected CI on the final head, and build from merged source. Release still
requires deployed source-hash verification and one complete three-fleet run with
verified committed journals and readbacks. Preserve existing driver runtime,
daily schedule and database storage. Keep timeout exhaustion visible if the
provider does not recover.
