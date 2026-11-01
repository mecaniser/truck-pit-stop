# DB-139 remaining held ETS rows

Owner: Backend & Integrations. Branch `codex/ets-remaining-held`, base `aa549f2e`. User authorizes source-confirmed corrections and exact blocker report for 61 rows/17 jobs. Financial display/link remediation only; no invoice/payment creation, restoration, balance rewrite or collection.

## Acceptance

Inspect all 17 source jobs and preserve tenant/customer/vehicle/payment/refund/freshness safeguards. Recognize only evidence-proven historical artifacts, retain real ambiguous evidence holds, count each canonical invoice/allocation once, and preserve existing accounting/export/outcome contracts. Require independent security/QA, focused negative tests, full production read-only comparison and financial invariants; operational FK changes require exact preconditions, audit/no-op/rollback verification.

## Runtime receipt — 2026-11-01

New checkout at aa549f2e with intake docs only initially dirty. Frontend `http://127.0.0.1:5202`, PID35722, cwd this checkout/frontend; API18021 `dieselbridge_api_ets-shared-billing` mounts this checkout/backend. Preserved approved root backend/.env and existing fictional postgres/truckpitstop_db139_shared, Redis11, sourcebinding shop1, empty completed-outcome mapping. No migrations, reseed, provider/worker or production configuration change. Proxy readiness200; signed-in browser C3 Fictional Shop1 and branch codex/ets-remaining-held@aa549f2 verified, paid existing fixture visible. Aligned and browser-verified before implementation.

## Source discovery

Fresh deployed reader confirms all61 rows still held. Historical captures and current source snapshots inspected; private row/financial details retained outside Git. Authenticated live ETS invoice pages confirm0384/0548/0709 paid and invoice-specific payments match totals. Source invoice pages for1304/1311/1381 return404PageNotFound while other invoices work; their16rows remain blocked on a current unique invoice/payment binding. More source cases under review.


## Live ETS source check (authenticated browser, 2026-11-01)

All 17 job invoice pages were visited directly using the source service number. Fourteen existing invoices matched preserved source snapshots; three returned authenticated404PageNotFound (1304/1311/1381). No source changes made.

| Job | Rows | Live evidence / proposed handling |
|---|---:|---|
|0384|5|Paid invoice0367, total/allocation2431.93; parent unapplied18.07 must never enter invoice amount.|
|0548|2|Paid invoice0518, total1346.86, allocations346.86+1000; parent unapplied0.14 excluded.|
|0709|2|Paid invoice0682, invoice allocation162.06; parent unapplied984.50 and other allocations excluded.|
|0979|8|Paid invoice0923, total3831.16, allocations831.16+3000; parent unapplied18.84 excluded.|
|1052|2|Paid invoice0993, total1009.22, source allocations1000+9.22; imported extra1009.22 has explicit historical reconciliation retirement evidence.|
|1146|4|Paid invoice1092, total/allocation3670.26; same-owner copy predates replacement canonical invoice after cleanup.|
|1302|3|Paid invoice1225, total/allocation557.87; local579.44 is unsupported by preserved or current source.|
|1305|3|Paid invoice1235, total/allocation908.55; historical copy names used fallback service1305.|
|1346|2|Paid invoice1269, total611.88, allocations45.38+566.50; local633.30 and same-owner artifact require separate guards.|
|1356|5|Paid invoice1306, total/allocation3931.66; local4202.30 plus fallback service1356 copy naming require separate guards.|
|0733|3|Paid invoice0767, total456.01, allocations450.33+5.68; live source confirms same customer and unique source vehicle117809, unit05Owner. Guarded owner vehicle-link plan pending.|
|0535|2|Source invoice0497 paid562.17, but repair-order owner customer/vehicle conflict and settlement remains tied to different customer. Cannot repair only the RO link.|
|1040|2|Source invoice0981 shows total215.59, payment217.60, balance-2.01. Genuine overpayment/credit, not supported by current zero-or-positive balance model.|
|1106|2|Source invoice1041 includes both +1026.98 and -1026.98 payments. Preserve reversal hold; paid label alone cannot establish safe payment accounting.|
|1304|4|Invoice page404; no current source binding/payment observation.|
|1311|3|Invoice page404; no current source binding/payment observation.|
|1381|9|Invoice page404; historical capture lacks invoice number and operation count differs.|

Expected bounded remediation candidates:36 display-only rows plus3 owner-vehicle rows;22 remain held. This is a proposal until negative tests, shadow and independent gates pass. Financial rows remain immutable.

Live ETS global search follow-up resolves the three404 cases further: service1304,1311 and1381 are all explicitly **Archived Canceled**. Same-number invoice search results belong to unrelated customers, proving a service-number fallback is not itself an invoice identity. Their16 rows retain unknown payment/balance rather than resurrecting cancelled work or borrowing an unrelated invoice. No source/work-status mutation.

## Shadow gate refinement

The first complete shadow restores28 rows, not the proposed36. The fallback roots1305 and1356 collide with actual live invoice numbers on other jobs (1396 and1443 respectively). The contract intentionally blocks these8 rows despite each source job showing paid. Do not suppress or repoint the other live invoices or weaken identity guards to reach an estimate. With the separate0733vehicle repair, expected total correction becomes31rows and30remain held. Final exact-source tests, shadow and independent approval pending.


## Implementation and local gates

200 focused tests pass. Final source SHA-256 `660931d560fdc493ab0a55922c47f5906b16376acd87669bc0f00f8d58b53c2f`. Exact full3739-row shadow changes28 target rows to paid;33still held before0733repair. Every unrelated response and fullfinancial/RO fingerprint matches discovery. Negative and real-database tenant/reference cases pass. Independent approval pending.

Signed-in local runtime confirms parent-payment excess is excluded: fictional parent544.41 with10unapplied displays invoice534.41 paid/remaining0, shared once. A source-only fictional amount discrepancy displays source524.41 paid/remaining0 and an amber Review needed tooltip stating ETS source amounts differ from imported financial records. Financial columns untouched. Existing partial/unpaid and identityconflict controls remain visible.

0733 operational candidate: finite1ownerlink/3row plan independently pending. Rolled-back serializable rehearsal applied/no-op/rollback/no-op passed and a fresh plan exactly matched the original. Financial/source/neighbor fingerprints restored; committedchanges0. Private artifacts outsideGit.
