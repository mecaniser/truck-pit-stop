# Shared CallRail request budget v1

ELIS PostgreSQL owns the allowance. Local requests and authenticated DieselBridge
requests reserve from the same ledger under the same account advisory transaction
lock before dispatch. The default shared cap is 1,350, leaving margin below the
provider's configured 1,500 free-request tier. Every attempt counts, including
HTTP errors, timeouts and lost reservation replies. No refunds or unguarded fallback.

## Account policy

An account has one budget owner: exactly one `api_budget_owner=true` CallRail
API credential, or the sole configured API credential for compatibility. Disabled
credentials remain in the ambiguity count. An ambiguous account fails closed.
The owner controls the account-wide invoice-period overage override; another
tenant cannot enable paid requests. The strictest configured limit and consistent
billing dates/timezone still apply to all configured credentials. The current
paid override remains valid through its existing invoice boundary and never renews.

## Signed client binding

Provision a dedicated enabled `CredentialReference` with provider `dieselbridge`,
purpose `callrail_budget_signing`, and a dedicated environment secret reference
(at least 32 bytes). Its tenant is the canonical ELIS account owner. Public metadata
contains the exact authorized DieselBridge `shop_id` UUID and canonical ELIS
CallRail `account_id`. Optional `provider_account_id` stores a verified numeric
DieselBridge alias for that same account. The request must match that configured
alias; locking, the ledger hash, limits and completion always use the canonical
account. Alias verification must use provider evidence (for example exact known
company-resource membership), never caller assertions or names.
Never reuse provider keys, webhook keys, session keys or media encryption keys.

Headers: `X-CallRail-Budget-Client` is that credential UUID;
`X-CallRail-Budget-Timestamp` is canonical Unix seconds (five-minute tolerance);
`Idempotency-Key` is a canonical UUID generated once per HTTP attempt;
`X-CallRail-Budget-Signature` is `sha256=` plus HMAC-SHA256 hex over:

```text
callrail-budget.v1\n{timestamp}\nPOST\n{exact_path}\n{request_id}\n{raw_body}
```

Bodies are bounded to 2,048 bytes. No provider payload, phone, message text,
attachment locator or provider key belongs in a budget request. HTTPS only at the
client; no redirects, automatic retries or environment proxy forwarding.

## Reserve and complete

`POST /integrations/callrail-budget/v1/reservations` body:

```json
{"request_id":"00000000-0000-4000-8000-000000000001","tenant_id":"00000000-0000-4000-8000-000000000002","account_id":"synthetic","purpose":"dbn_sms_send"}
```

Other allowed purposes: `dbn_mms_manifest`, `dbn_mms_image`,
`dbn_tracker_inspection`. The tenant and account must match server-side binding.
The stored reservation UUID is `uuid5(signing_credential.id, str(request_id))`.
The transaction commits before a first-grant response has `dispatch_allowed=true`.
A replay always returns `dispatch_allowed=false`; changing purpose returns409.
Lost replies remain counted and authorize no dispatch. 429 is an exhausted cap;
503 is unavailable configuration/baseline. Both block provider dispatch.

`POST /integrations/callrail-budget/v1/reservations/{request_id}/completion`
uses the ORIGINAL request UUID in path and Idempotency-Key, not the stored UUID.
Body is `{"http_status":200}` or `{"http_status":null}`. Same outcome is idempotent;
a changed outcome returns409. Completion failure never triggers another SMS or
provider request. Missing completion remains counted as an unfinished reservation.

## Scope and rollout

Reserve every manual SMS POST, each discovery page, authenticated API media GET,
and tracker-inventory diagnostic GET. Direct signed storage transfers do not
consume a developer API unit. Cached images/manifests require no reservation.
Tests use synthetic keys and mocked transports only.

Deploy ELIS broker first, provision dedicated binding/secret and explicit owner,
then deploy guarded DieselBridge Web and Worker before the next invoice period.
Missing configuration fails closed. Record exact revisions and cutover time;
historical DieselBridge use is not retroactively attributed. Verify mixed-app
last-slot races, expiry, replay, completion, and both loaded runtime identities.

Rollback must retain the broker and guard. Pause dispatch rather than restore an
unguarded DieselBridge revision. Other external/manual uses of the provider keys
are outside these two applications and require separate accounting. A cap cannot
constrain a key used outside the guarded code.
