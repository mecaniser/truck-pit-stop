# DB-048 full-cash safeguard acceptance

Local candidate baseline: a5f243ca0e1d7fc83a5b13149246446fbc9ab26a.
Accountable implementation: Backend & Integrations. Release: Release & Reliability.

## Independent acceptance

- Backend owner suite: 239/239, including 28 cash tests.
- Independent Security/local QA: 114/114 backend, 34/34 frontend; P0/P1/P2: 0/0/0.
- Frontend production build, TypeScript and changed-source lint pass.
- Desktop and 390px local fixture: full-only amount, explicit receipt confirmation,
  keyboard-accessible controls; no horizontal overflow. No real payment submitted.
- Disposable PostgreSQL16: fresh migration140, standard-data downgrade/re-upgrade,
  cash-data downgrade refusal and local-policy immutability pass.
- Independent PostgreSQL races pass: cash/card both orders; cash/export with and
  without an existing settlement; void/cash/export; realm reset/export; worker busy
  requeues its owned lease with zero provider calls. Busy is a safe retryable denial.
- Reproduced pending legacy Zelle and historical realm-reset evidence holes were
  corrected and independently rechecked. A missing provider ID alone never proves
  that an invoice is safe to convert to cash.
- Nonzero service-tax and card-fee fixture preserves the invoice snapshot while
  collecting only full principal and service tax, not an unearned card surcharge.

## Frozen reviewed blobs

| Artifact | Git blob |
| --- | --- |
| Cash service | 4bd782d0335d279057838a97f4b0ec81913a52a4 |
| Policy/locks | c25122293838c271d0b0ad6dd47406219dd5d01e |
| Export worker | a53e77aaf072466d1ca0401b7146ac079995733f |
| Migration140 | 8d6318bb34fc43f1300591f8bd11f3a9e3c0f9c2 |
| Backend cash tests | f2f0ab02af4ef4a5490920466ca3900c32f9457f |
| Cash frontend | 02d7d983f35b69cbd0e4198bba854afecac9e57c |
| Frontend cash tests | 5ab2dda2e683731c775566e501a8b9ba33db6ea5 |

## Release boundary

Protected PR CI remains required. Apply140 before running cash-aware code.
Verify all invoice-export workers are guarded before exposing the API/UI. No live
cash receipt is needed for smoke testing. After cash data exists, retain schema
and guarded workers/API; disable entry and forward-fix rather than downgrade to
unguarded writers. Production-sized DDL timing must be observed during deployment.

Nonblocking P3: direct SQL can update additional cash-attempt provider fields without
firing the narrowly scoped trigger. No exposed application path was found; broader
SQL trigger hardening is backlog. Fleet, cash CSV/analytics and cash reversal UI
are separate work, not shipped by this change.
