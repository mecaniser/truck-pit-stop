# DB-036 health login context recovery contract

Architecture decision: **GO for a health-only bounded pre-credential recovery implementation**, subject to the invariants and independent gates below. This is not a QA, security, deployment, or production-data approval.

Backend & Integrations owns implementation; Release & Reliability owns rollout. The existing DB-036 worker item owns this outcome. No schema, API, tenant, importer, schedule, restart-policy, credential-setting, or other-collector contract changes.

## Evidence and intended outcome

The deployed health collector already calls `prepareLegacyLogin`. The October 29 04:32 UTC run stopped on `login_legacy_redirect_loop` after the helper's two validated provider-link clicks returned to completed lookup documents. A later credential-free probe on the same cloud egress returned to lookup after its first click and reached the legacy form after its second click. Transient public login transitions are observed; a cookie/session cause is not established.

The change may recover one exhausted **anonymous public-form preparation** using an isolated fresh context. It must not retry credentials, collection, import, or an ambiguous application outcome. Do not describe it as a permanent fix for provider availability or as proof of a cookie defect.

## Entry and eligibility

1. Scope the new orchestration to `motive_health/collect.cjs` or a health-only helper. Keep the reviewed shared helper and its existing two-click/new-document rules compatible and unchanged for other workers.
2. The first context uses the existing timezone, locale, headless browser, official app navigation, auth redirect wait and exact trusted origin/form validation.
3. Only the synchronous orchestration state before any email/password fill or login submission is eligible. Credential operations occur outside and strictly after successful orchestration returns.
4. Catch only `login_legacy_redirect_loop` thrown by the first invocation of the reviewed shared form helper. Do not catch a larger navigation/collection/import block and infer that the same error text proves eligibility.
5. Wrong origin, credential-bearing URL, ambiguous form, unsafe/missing link, navigation error, form timeout, unknown error, or any post-credential failure is terminal. No fresh-context recovery for those cases.

## Deadline and bounded lifecycle

- Start one absolute 15,000 ms form-readiness deadline immediately before the first shared-helper invocation. Initial navigation retains its existing separate timeouts.
- Pass only the remaining readiness budget to the first helper and, if eligible, every recovery operation. Never reset the deadline when creating the fresh context. A monotonic clock is preferred for the wrapper. If no time remains, fail before creating or navigating a replacement context.
- Dispose the original anonymous context before creating a replacement; a disposal failure is terminal. Close all old pages and let the shared helper's `finally` remove its listeners. Do not clear/reuse cookies or storage in place.
- Create at most one replacement context on the same browser with the exact existing options and **no storage state, cookies, tokens, persistent profile, or copied session**. A second exhausted loop fails closed.
- Perform the existing official app-to-auth bootstrap in the new context. Navigation and auth waits are individually capped by the remaining absolute readiness budget, then invoke the same helper with the remaining budget. Reapply the existing default page timeout for the successful page's later operations; do not retain an accidentally tiny login remainder for collection.
- The shared helper still permits at most two provider-link clicks per context, with the second only after a completed new-document return. The wrapper adds no link clicks of its own. No lookup/SSO submit, guessed direct endpoint, request interception, private API, security-check bypass, or extra credential submit.
- Preserve the existing worker/collector overall deadline. Browser and active context close on all terminal paths, including replacement creation/navigation failure. No second browser launch or unbounded loop.

Return only the successful `{context, page}` pair to the existing credential flow. On success, the caller fills the same unique legacy credential fields and submits once, then runs the existing company, source completeness and importer/receipt gates. On terminal failure, collection remains incomplete and no import begins.

## Diagnostics

Use static stage/reason metadata for initial preparation, one context recovery, recovery success or terminal failure. Never log credentials, page text, URLs with query strings, network headers, cookies, tokens, or exception bodies. Preserve the original typed failure where possible. A successful normal run without a recovery stage does not prove that the live recovery branch was exercised.

## Acceptance and negative fixtures

Exercise the actual health collector boundary and real Chromium routed fixtures where appropriate:

- Existing direct legacy and first/second-click lookup success: one context, one credential submission, normal collection contract unchanged.
- First context confirms two completed lookup returns, replacement reaches valid form: exactly two contexts, old context closed before replacement, one credential submission only on replacement.
- Persistent replacement loop: bounded failure, zero credential fills/submissions and zero collection/import.
- Wrong host/path or credential-bearing URL; ambiguous/missing credential form; unsafe/duplicate legacy link; unknown error: no replacement and zero credentials.
- A hash change, pending click, or subframe navigation never grants a second click.
- Deadline exhausted before replacement: no replacement. Time spent closing, creating and navigating replacement counts against the same deadline; helper timeout never becomes zero/negative or resets to 15 seconds. Creation/navigation/cleanup failures abort and close resources.
- Failure after credentials or after successful form preparation never re-enters recovery.
- Existing company/scope/source/idempotency tests and static diagnostic redaction tests remain passing.

Independent QA and Security must review the concrete implementation and tests. Architecture authored this contract and must not approve its own directed implementation as an independent gate. Protected exact-head CI, merged-tree/archive parity, preserved deployment manifest, and one legitimate new-image runtime run with exact source/receipt/persisted readback/replay acceptance remain release gates. Distinguish normal-path runtime acceptance from fixture-only recovery-branch evidence. Do not start a service solely for SSH or enable a Codex automation.

## Implementation preflight

October 29 UTC, branch `codex/health-login-context` from `3fdafd12`. No listeners on 5173/8000. Mandatory runtime controller dry-run is blocked by missing approved backend/.env and frontend Vite; no services started, secrets copied or local UI readiness claimed. The change is a worker pre-credential boundary; isolated Chromium fixtures and subsequent authorized production runtime acceptance provide its relevant browser evidence.

## Owner source verification

The helper is health-only; the shared legacy helper is unchanged. An additional guard requires the trusted lookup page and no visible legacy credential fields before the eligible context replacement. Actual collector fixtures prove exactly one browser launch and one credential submission after recovery, and no credential operations on terminal paths. Replacement page operations retain the normal 15-second default timeout after successful preparation.

Owner verification: 71 Node checks pass, including real Chromium isolated routing, actual health collector wiring, shared login fixtures and diagnostic redaction; eight focused health worker Python tests pass. New Chromium fixtures are included in the existing protected workflow. Normal-path runtime acceptance remains separate from fixture-only recovery-branch evidence. Independent QA/Security and protected exact-head CI remain required. No production mutation or Codex automation was performed.
