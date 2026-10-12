# DB107 independent QA review

Reviewer: fresh `conversion_qa` agent, 2026-10-12. The reviewer has not implemented
or directed the implementation and owns this evidence file only. Source branch:
`codex/recommendation-conversion`, initially based on `e22e9b0d` (uncommitted DB107
implementation under review). Parent owns the intentional combined runtime and
all database/schema changes; QA has not restarted or migrated any service.

## Current gate

**GO for local DB107 acceptance.** Reviewed source `2075ccfc` and combined preview
`b25bafc1`; all blocking QA findings are corrected. The independent reviewer ran
the automated checks and inspected the owner's actual browser screenshots,
interaction receipts and runtime identity, without implementing the feature.
This is not a release approval. Security separately records GO; protected CI,
merge and deployment remain separate gates.

## Independently reproduced findings

1. **Deleted-target regression test failed.** Initial focused frontend run:
   57 passed, one failed. `PriceBuilderPanel.recommendations.test.tsx` waited for a
   queried operation while the deleted-target query is intentionally disabled.
   Parent corrected the fixture to provide a genuinely stale cached summary;
   no product behavior change was required. Recheck follows below.
2. **Conversion preview and saved amount diverged at a rounding tie.**
   `0.50 hours × $145.01` displays `$72.51` with the UI's `Intl` rounding but saves
   `$72.50` through canonical Decimal half-even rounding. Independently executed
   both expressions. Returned to Frontend to use exact monetary rounding and a
   regression case.
3. **Explicit resolution errors were silent.** The source recommendation Resolve
   mutation had no error handler or error display. After the linked operation is
   cancelled/removed in another session, stale `can_resolve` permits a click that
   receives the new 409 guard without showing any reason or recovery. Returned to
   Frontend to surface the structured message and retry/refresh.
4. **Reduced-role error provenance disclosure.** Review identified the existing
   mechanic/fleet recommendation PATCH invoking the new resolution guard, which
   returned cross-order conversion details in its 409. Sent to the independent
   Security reviewer, who reproduced it and returned it to Backend. Security owns
   its remediation verification and separate gate.
5. **A stored conflict could override a later authoritative refresh.**
   `effective = conflict ?? conversion` retained an old active 409 conversion even
   after Refresh returned a removed/cancelled conversion eligible for replacement.
   The user could not see Add again until the panel remounted. Returned to
   Frontend for prop/conflict reconciliation and a rerender regression.
6. **Historical vehicle snapshot drift could falsely free an active link.**
   Review queried the target vehicle mismatch branch in derived state. Ordinary
   RO PUT cannot change vehicles, as Backend confirmed, but canonical vehicle
   merge drift could make a real existing operation appear unavailable and
   replaceable. Backend is retaining active duplicate protection across snapshot
   drift and adding its regression.
7. **New mobile confirmation/error text needed scoped contrast.** The320px
   replacement screenshot showed pale warning text against the light form. The
   global presentation rule overrides `text-amber-800` with the warning500 token;
   the equivalent red500 error token also falls below4.5:1 on white. Returned to
   Frontend for dark, scoped text on the conversion surface and recapture.
8. **Restore/reactivation guard explanation was discarded.** Existing
   `getErrorDetail` accepted only string detail, so the new structured
   `superseded_recommendation_work` guard became a generic Failed to restore/reopen
   toast. Returned to Frontend to preserve the safe structured message.

Findings 1–3,5–8 are corrected and independently rechecked. Finding 4 and later
Security discoveries (history-event disclosure and activation serialization) are
recorded by the separate Security reviewer; their owner-added focused tests also
pass in the independent QA rerun.

## Automated evidence

- Initial backend isolated API suite: `test_db107_recommendation_conversion.py`
  and `test_db099_recommended_work.py`: **49 passed**. This run predates the later
  lifecycle and Security regression additions; it is not the final acceptance run.
- Frontend corrected source `d8b446be`: **60 passed** across conversion action
  (20), price-builder navigation (5) and recommendation continuity (35). The
  rounding correction is covered, the stale deleted-target test passes, and
  source inspection confirms Resolve errors now toast the structured message and
  refetch recommendation state for recovery. Findings 1–3 are corrected.
- Existing backend price-build service, fleet-manager price-build access and
  status-set regression suites: **36 passed** independently.
- Final frontend after conflict reconciliation: **61 passed** (21 conversion
  action,5 navigation,35 continuity); source correction commit `c98bf023`.
- Final source `2075ccfc`: **126 independently passing frontend checks**:
  61 conversion/navigation/continuity plus65 price-builder pending-feedback
  regressions, including fresh completion confirmation after switching orders.
  Structured lifecycle guard messages now use the safe message parser; conversion
  error text has a scoped dark color. Owner source build passes; no product
  change occurred in the later combined notification-test mock correction.
- Final affected backend API suites: **55 passed**, including fault-injected503
  replacement rollback, provenance after edit/removal, unavailable-target replay,
  explicit replacement, cancelled/deleted restoration guards, no automatic
  resolution, explicit resolution guards, role/tenant checks and source snapshot
  drift. Failed replacement keeps the original current conversion, adds no labor
  or history event, and succeeds when retried with the same UUID after recovery.
- Real PostgreSQL suite: **5 passed independently**, using the pre-provisioned
  disposable `db107_conversion_20261012` database on local55439. Scenarios cover
  same-key/two-key/two-target concurrent conversion (one conversion, one labor,
  one history event), plus customer/internal activation serialization during
  cancellation. No migrations or service restarts were performed by QA.
  Backend final correction commit: `9a633b5b`. Independent Security records GO at
  this same source revision in `DB107_SECURITY_REVIEW.md`.
- Newly affected fleet workflows and mechanic hold notification regressions:
  **84 passed** independently after the lifecycle lock additions.
- Existing SQLAlchemy/Pydantic deprecation and React Router/Browserslist warnings
  were observed; none were test failures.

## Runtime evidence

The parent integrated the implementation into the preserved combined local
preview at `http://127.0.0.1:5174` / API8001. Browser interaction was performed by
the implementation owner through CUA; the independent gate reviews its visible
evidence and receipts in addition to independently executed tests. No physical
phone testing is claimed.

Independently corroborated the settled preview at `0ccd3bd5` on branch
`codex/ets-parity-preview`: FE5174 listener PID68993 has cwd preview/frontend;
API8001 container binds preview/backend. Readiness reports database/Redis healthy.
Redacted DB identity is postgres / `truckpitstop_ets_workflow_parity_20261012`,
Redis9; Alembic reports the single merge head `167_merge_checklist_conversion`.
The earlier read caught the owner's cherry-pick in progress and was deliberately
not treated as a readiness result. No service was stopped by QA.

Independently inspected `output/db107/desktop-converted.png` (1280×720): the real
rendered operation, original source link,30m/$145.01 inputs, persisted$72.50 and
bottom actions are readable. Source/reload/replacement/error/mobile evidence is
recorded below; each still image proves its displayed state only.

Independently inspected `mobile-390-form.png` and `mobile-390-retry.png`: entered
1:30 hours/$145 rate, reviewed$217.50, whole button labels, retained values after
failure and Retry safely are visible. The original320px image exposed poor warning
contrast and a form below the footer; owner corrected scoped color and workspace
scroll reveal. `mobile-320-replacement-fixed.png` independently confirms the full
dark warning, hours/rate, total and complete Cancel/Add replacement actions above
the footer. Parent DOM receipt: width/scrollWidth320; inputs and buttons44px high;
inputsY226–270, actionsY314–358; warningrgb(120,53,15). Parent reports actual Add
replacement created labor `1f6db4fb-5746-425a-bc43-42bf9617170f`, total$217.50,
retaining the source. These are viewport checks, not physical phone tests.

Final owner interaction receipts and independently reviewed evidence:

- Desktop and phone conversion create exact manual work, retain source provenance
  and keep the recommendation unresolved. Same-order links focus the exact labor
  row; source and reverse navigation plus reload retain the same identities.
- `mobile-390-retry-fixed.png` shows a dark readable failure message, retained
  hours/rate, safe explicit Retry and the unchanged existing total. Parent
  computed error color isrgb(153,27,27). No unknown response becomes a second Add.
- `mobile-320-converted.png` shows the resulting$217.50 operation and original
  source link. Two removed mobile operations are retained as superseded records;
  one current conversion survives. The restored form screenshot confirms all
 44px controls above the footer with width/scrollWidth320.
- `desktop-linked-operation-final.png` shows an edited operation description
  while the original source description/link and$72.50 remain intact.
  `desktop-resolved-readable.png` shows explicit Resolved state and a readable
  exact target link. The source recommendation stays available after resolution.
- Completion boundary: parent used the normal UI to reach pending_review, then
  prepared only synthetic `QA107-DESKTOP` status to completed to avoid the
  unrelated Finalize & Send Invoice flow. The independently inspected
  `fixture-completion-receipt.json` confirms unchanged totals, invoices, payments
  and provider outbox, and no automatic source resolution. Explicit Resolve was
  then clicked through the actual UI. Invoice finalization/payment is not claimed
  as an end-to-end browser test of this feature.
- Unavailable-target recovery: actual UI created15m×$145 work on
  `QA107-RECOVERY`, soft-deleted it through Order actions/Delete confirmation,
  displayed its deleted state on `QA107-MOBILE`, and required explicit Add
  replacement. The new labor is `26c1bdb7-4b2d-4d87-8473-006830dcfe72`; mobile
  total$253.75 is two distinct recommendations, one current operation each.
  `desktop-deleted-target-replacement.png` confirms the reviewed replacement
  state. Deleted filter → QA107-RECOVERY → Restore order is blocked with the
  exact explanation in `desktop-restore-blocked.png`, preventing two executable
  copies. This customer UI exposes Delete/Restore, not Cancel; cancellation is
  verified by API and real PostgreSQL tests, not claimed as a visible UI action.
- Final combined preview `b25bafc1` has no tracked modifications, database/Redis
  readiness is healthy, and the owner log `/tmp/db107-preview-integration-fix.log`
  reports82 passing combined checks. Its final change adapts test mocks to both
  checklist and conversion guard reads; both application guards remain intact.

## Nonblocking observation and limits

The existing deleted-order shell still requests DB099 recommendations with a
deleted context and displays its truthful stale-page refresh error. Conversion is
disabled and the tested restoration guard remains usable. Hiding that optional
panel on deleted orders is a separate small shell refinement, not a duplicate or
provenance defect and not a blocker for this local acceptance.

Only isolated synthetic local fixtures were mutated. QA ran additional unique
synthetic PostgreSQL fixtures in the dedicated disposable database. No production
migration, deployment, real invoice/provider operation, or physical phone test was
performed by this gatekeeper. Owner retains final runtime cleanup and PR/CI work.
