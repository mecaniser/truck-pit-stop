# DB-036 login failure diagnostics

Owner: Backend & Integrations. Status: Review; no merge or deployment authorized.

All five collectors label navigation, auth redirect, origin validation, email fill,
password fill, submit, and application redirect separately. The shared failure
handler emits `collection_failure_diagnostic` with static phase and error-kind
allowlists. Network resets/closures/timeouts/network changes are distinguished
from Playwright TimeoutError. No browser message, URL, page content, screenshot,
credential, cookie, or tenant identifier is emitted. Existing supervisor failure
classification, retry decisions, login actions, timeouts and import gates remain
unchanged.

Validation: 103 offline collector Node tests passed. Fault injection covers each
login action in all five collectors and wrong-origin refusal before credential
fill. Independent QA/Security GO for diagnostic PR only. Protected CI includes
the new tests. No production login, collection, deployment or trigger performed.

Local runtime: isolated /tmp/db036-login-diagnostics, branch
codex/motive-login-diagnostics, base 1119a392. No listeners on 5173/8000; no local
credentials copied. No browser acceptance claimed. This worker-only diagnostic
was tested with offline fixtures. Production cause remains unproven until an
explicitly approved diagnostic rollout captures the failing operation.

Rollback: revert diagnostic additions; they change observability only. Deployment
and natural-run acceptance remain separate, unapproved steps for this follow-up.
