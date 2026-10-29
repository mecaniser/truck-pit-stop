# DB-036 direct release evidence — October 29, 2026 UTC

Release & Reliability owns this release. The human authorized direct fuel catch-up deployment, duplicate-safe missed-day verification, and drivers crash resolution. The Codex heartbeat was deleted and remains off. Production collector schedules are unchanged.

## Fuel: released and bounded runtime acceptance passed

- PR [660](https://github.com/mecaniser/truck-pit-stop/pull/660) merged as `4595998cd35f3a76e4eba76d66b9aad6572292cc`. All seven checks in run `40393128705` passed on reviewed head `c2cc0980b23dad329ceb2713e26134a53e368af6`.
- The previously pending diagnostics gate was reconciled from exact saved evidence: canary `20261026T200054Z-937b79b4-b2cf-4247-bd1c-faf39de774bd` had 7 created and 31 unchanged rows; all 38 passed source/normalized hashes, scope, readback and replay. Pending receipts: zero.
- Independent release review compared all 2,285 tracked archive files, except the preserved service-specific `railway.json`, with the merge. No mismatches. Seven deployed worker module hashes also match the archive exactly.
- Deployment `2f2b6f77-6973-4e84-a5b1-260dfc434ed8` succeeded. Image: `sha256:65a2e730a1092cbfba3e8227f5365795361af68a3c895c348d8e011be5092df8`.
- Full service manifest and `/data` mount match the diagnostics deployment. Normal command, 13:30 UTC cron, restart NEVER, one replica, commit enabled, empty manual bounds and maximum seven dates are preserved.
- An initial empty upload `fa7009de` was canceled while INITIALIZING and became REMOVED. It was build-only and never executed. The corrected exact archive was then uploaded once.

Exactly one controlled normal run started at 01:30:06 UTC and completed at 01:52:50 UTC, within the existing 30-minute collector budget. Its immutable automatic plan was `93a96619-9e9b-41de-adbb-8f1dd8bc6f93`. One login and directory pass supported 161 reports: 23 providers across seven dates.

| Report date | Saved rows verified | Created | Unchanged replay | Coverage |
| --- | ---: | ---: | ---: | --- |
| 2026-08-15 | 5 | 0 | 5 | Examined with exceptions |
| 2026-10-25 | 7 | 0 | 7 | Examined with exceptions |
| 2026-10-26 | 16 | 0 | 16 | Examined with exceptions |
| 2026-10-27 | 17 | 0 | 17 | Examined with exceptions |
| 2026-08-16 | 1 | 0 | 1 | Examined with exceptions |
| 2026-08-17 | 6 | 0 | 6 | Examined with exceptions |
| 2026-08-18 | 6 | 0 | 6 | Examined with exceptions |

All seven daily receipts are committed and verified, with exact source/normalized hashes, scope, run path, day and saved IDs. Independent fresh SELECTs matched every saved ID and semantic request digest. Readback and unchanged replay passed for all 58 saved observations. No new fuel rows were inserted: the selected dates already had saved rows from prior runs.

The table remains 716 rows and 716 unique source keys. The original 675-row subset retains digest `389710ddd74929cf57b8f99b48c3b862`. The audit used tenant-scoped SELECTs inside READ ONLY transactions; no importer calls or raw production record exports. Secrets were not written to evidence files or printed.

The durable next plan alternates to the recent lane and advances backlog to August 19–21. The complete-through boundary remains null. The seven day matrices retain 95 source-absence observations, 14 identity-exception observations and one immutable source conflict on October 26. These are observations across dates, not unique vehicle counts. No absence is treated as zero, no changed reading overwrites an immutable saved row, and no full-history completeness is claimed. A separate date-count audit found saved rows on every date August 15–October 27; it does not prove complete per-vehicle coverage.

Independent QA/Security gave runtime GO for this bounded catch-up and idempotency result. The existing cron can continue durable catch-up without Codex wakeups.

## Drivers: crash diagnosis and scoped fix

The October 27 execution on deployment `226f9c85` failed at 13:49:57 UTC with `login_email` / `browser_timeout`, followed by `driver_collection_failed` / `ui_timeout`. Railway stores structured events in log attributes while the message field is blank; this explained earlier empty log checks. The saved logs do not establish which provider DOM appeared.

The externally redeployed October 28 same-image run was independently accepted: three durable journals, 21 records, matching source/attempt hashes, scope and identities, committed receipts, readback, unchanged replay and projections; no unverified assignments. That establishes recovery of that run, not permanent resolution of transient provider behavior.

Drivers bypassed the trusted login-form preparation already used by sync. PR [661](https://github.com/mecaniser/truck-pit-stop/pull/661) adds the existing helper after the origin guard and before credentials. It preserves selectors, credential settings, import contracts, schedules and retry policy. Independent QA/Security passed 76 Node/Chromium tests. Owner checks also passed 29 Python tests; two optional local PostgreSQL tests were skipped, while protected backend CI passed. All seven checks in run `40800729481` passed on head `1bdd4c7046a561b99f1795dd6a594f8a5e179c39`.

PR661 merged as `2ada2792b3c957e4990a9c2c51d55d7b3a52399e`; checked and merged trees match. Drivers-only deployment `8b59264a-592b-4489-a045-9b653c9b9111` succeeded with image `sha256:d5c9c9005292c7f4d2f6e3c4ecebc072be6b15d26a168f3947d019d50f243746`. Full manifest, empty mount set, 13:45 UTC cron, restart NEVER and one replica are unchanged. Deployed collector and trusted helper hashes match the merge archive.

Exactly one controlled drivers verification run began at 01:53:22 UTC after fuel exited. It passed the new login-form check, one credential submit, company verification and complete collection. At 01:58:57 UTC, the worker reported one source collection and three verified committed fleet projections.

The bounded SELECT-only observer exited successfully. Three distinct fleet journals created at 01:58:51 UTC passed exact source/attempt hashes, tenant/actor/company identity, committed receipt validation and fresh saved capture-ID checks. Eligible/readback/replay/projection counts were 1 + 1 + 19 = 21, with zero unverified assignments. Initial and final deployed collector/helper hashes matched the merged archive. This verifies the changed login path and successful full run; it does not guarantee that future provider outages cannot occur.

## Rollback and limits

Fuel rollback reference is the prior diagnostics image `3e7ba872`; drivers reference is the prior `86b1db48` image. Do not delete durable evidence or blindly trigger after an ambiguous commit. Reconcile exact saved intent before any new capture. These releases do not change authentication settings, credentials, production schedules or unrelated workers, and do not establish sustained recovery of all five collectors.
