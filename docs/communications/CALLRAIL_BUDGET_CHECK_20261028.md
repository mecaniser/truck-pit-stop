# Shared CallRail budget after override expiry

Checked October 28, 2026 at 21:28 America/New_York (October 29 01:28 UTC).
DB-COMMS-022; Product & Delivery Lead accountable. Read-only operational evidence.

The deployed ELIS broker at 607dba2d evaluated its actual account_budget function
against production data inside an explicitly READ ONLY PostgreSQL transaction.
No provider request, budget reservation, SMS, customer media read or database write occurred.

| Field | Observed value |
|---|---|
| Period start | October 28 04:00 UTC |
| Period end | November 28 05:00 UTC |
| Limit | 1,350 |
| Used / recorded | 42 / 42 |
| Remaining | 1,308 |
| Accounting complete | true |
| Paid overage allowed | false |

Current-period ledger purposes: DieselBridge MMS manifest 1, DieselBridge MMS
image 1, matching 9, reconciliation 5, revision sweep 1, transcription 25.
This establishes that both applications contribute to the current shared ledger.
No provider billing observation exists for this new period; the figures describe
application-metered use, not an independently reconciled provider invoice.

The expired override no longer permits overage. Existing meter enforcement rejects
incomplete accounting or used >= limit when overage is false. Prior release
synthetic last-slot race/exhaustion tests are recorded in the release receipt.
This read-only check does not deliberately exhaust the live allowance or claim
an observed production 429 at the limit.

Fresh Railway configuration reads confirm SMS_TENANT_ROUTING_ENABLED,
SMS_AUTOMATION_OUTBOX_ENABLED and SMS_RECOVERY_ENABLED are unset on both
DieselBridge Web and Worker; their code defaults are false. No settings changed.

Result: expiry and current shared accounting verified. No corrective change needed.
