# DB-036 location collector authentication recovery

Backend & Integrations owns this high-risk worker correction on
`codex/motive-location-auth`, base `9ad6809e`. Independent Security and QA,
protected CI and scheduled runtime acceptance remain required.

## Evidence and outcome

Read-only production investigation on November 4, 2026 New York confirmed the
five-minute `DBN-motive-sync` worker is enabled for saving but three checked
executions fail in `login_legacy_redirect_loop` before credential entry,
collection or import. The latest checked execution ran November 5,
04:37:18–04:37:25 UTC. Current Fleet projection retains 21 stale speed readings
and 21 stale locations, with four null units. The newest location capture is
November 4, 09:03 UTC. The separate health worker's successful mileage and
engine-hours collection does not restore this location worker.

## Authentication interface

Reuse the released health authentication implementation through a location
adapter; do not fork or relax its form/ownership rules. `prepareSyncLogin`
retains its `(browser, options)` interface and legacy result. Existing configured
Motive credentials enable the reviewed native lookup fallback only after the
exact persistent anonymous legacy redirect loop. Successful fallback returns
`{ context, page, authenticated: true }`; only then does the location caller skip
its existing legacy credential submission. Without both fallback credentials,
legacy-only behavior remains unchanged.

The approved fallback disposes anonymous contexts, uses one additional isolated
context and one fixed 15-second budget, verifies official HTTPS routes and native
form ownership/actions, submits lookup once and password once, and rejects
ambiguity, wrong account, unsafe targets, SSO redirects and challenges. No
password retry, session copying, private endpoint or bypass is introduced.
Location diagnostics use static `sync_login_*` names; no credentials, field
values or authentication URLs enter logs.

The repository location manifest uses the pinned drivers Dockerfile, while the
actual cloud service metadata uses `backend/Dockerfile.motive-sync`. Both copy
the entire backend, including the reused health helper and shared dependencies.
The release artifact must preserve the actual cloud build/deploy configuration,
not silently substitute the repository manifest. Verify the exact dependency
chain and absence of circular imports; no service Dockerfile, cron, replica,
mount, environment, scope or image-base change is part of this correction.

## Acceptance criteria

- Persistent anonymous legacy redirects can reach the reviewed native flow with
  exactly one username POST and one password POST. The actual location caller
  does not submit credentials again after successful fallback.
- Legacy success and existing anonymous context recovery remain intact.
- Unknown errors, ambiguity, unexpected routes, challenges, wrong hidden account,
  rejected credentials and deadline/disposal failures remain terminal.
- Credential POSTs stay on the exact approved official authentication endpoint;
  unrelated hosts receive no credentials or session data.
- Company and timezone verification still precede source collection; a wrong
  source company cannot produce a complete source or import.
- Existing VIN/membership checks, source timestamps/precision, speed parsing,
  inline-location-only speed exclusion, five-minute display freshness, receipts,
  worker lock, cron and commit settings remain unchanged.
- Focused Node/isolated Chromium tests and fresh independent gates pass. Later
  authorized scheduled production collection/import and exact source/receipt/
  current Fleet readback are required before Done.

No telemetry schema, API, migration, UI or customer-data change. Deployment and
provider execution are outside this implementation handoff.
