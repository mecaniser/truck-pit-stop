# DB-COMMS-016: incoming CallRail attachment receipts

Owner: Backend & Integrations. Existing signed callback/API/tenant contract remains unchanged.

## Acceptance

- Valid inbound MMS, including an empty text body, produces one normal inbox message/inquiry using existing company, receiving-number, contact, provider-ID and sender-provenance validation.
- Preserve any text caption exactly; append a plain attachment notice indicating the file remains in CallRail. A media-only receipt uses that notice as its body. No claim that native attachment viewing is implemented.
- Never fetch, persist or expose media URLs or credentials. No outbound MMS capability or provider configuration change. Existing UI displays the normalized body using its current text-message contract; no migration.
- Normalize deterministically before duplicate comparison. Provider aliases, timestamps, unread counts and automatic reply-number evidence retain existing behavior. Expired media URL changes cannot create duplicate messages.
- Preserve STOP/opt-out handling on caption text; do not let the attachment notice hide a STOP caption. Malformed content/type/media containers remain quarantined.
- Reject outbound MMS in this bounded change; do not reconcile an MMS callback against pending manual SMS. Existing plain SMS callbacks remain unchanged.
- Recovering the reported production receipt is a separate scoped, audited inbound operation after release. Keep original quarantine history and media safely in CallRail; no blind replay or outgoing message.

## Verification

Synthetic payloads only in tests. Include empty/captioned MMS, sms plus media, duplicate with refreshed media locator, malformed fields, company/receiver isolation, disabled intake, suppression and original SMS regressions. Independent QA/Security required. No real customer data, attachments or private identifiers in repository fixtures.

## Verification receipt: 2026-10-21

Read-only production investigation matched the reported 16:10 EDT inbound receipt: its message type was MMS, its text body empty, and its quarantine reason `unsupported_message`. The deployed callback and service source match this branch's base. No customer identifiers, provider IDs, attachment content, or media locators are included here.

- Owner: 22 synthetic SQLite cases passed, including the signed ASGI callback, invalid signature, duplicate replay and existing message JSON contract.
- Owner: 59 isolated PostgreSQL inquiry/service regressions passed in a separate process.
- Fresh independent QA/Security: the same 22 and 59 cases passed, plus five direct normalization boundary assertions; GO with no production or provider actions.
- The first mixed SQLite/PostgreSQL invocation encountered fixture type errors because the existing SQLite conftest rewrites model UUID types globally. Separate fresh-process runs passed; no fixture, guard or test was removed to hide the failure.
- Local synthetic database was migrated independently through `187_labor_twilio_merge`; runtime preflight verified intended worktree, loopback database, direct/proxied readiness and three false SMS flags. That process stamp predates implementation, so it is not evidence of a final served browser acceptance.
- No frontend changed. ASGI callback-to-message JSON coverage verifies the changed runtime contract; native attachment viewing and a new UI are outside this correction. Protected CI, deployment and live acceptance are pending.

## Scoped recovery after release

The correction accepts future valid receipts; it does not automatically replay quarantine history. After the release is authorized and verified, restore only the originally identified inbound MMS through `apply_event` with its original binding, payload, timestamp and provider aliases. Keep current company/number/tenant/identity, intake, age and duplicate checks active. Record the resulting message ID on the original quarantine resolution without deleting its history. If any current guard blocks restoration, stop and investigate instead of bypassing it. Repeating the scoped receipt must return the same message without adding unread counts. Verify the message in the signed-in inbox and preserve its receiving-number reply route.

No restoration has been executed. Do not send an outbound message, import unrelated history, fetch the attachment, enable SMS flags, or alter CallRail webhooks/forwarding as part of recovery. The attachment remains viewable in CallRail.

## Prerequisite CI correction

Candidate663c0621 exposed an existing error-persistence hard-deadline cleanup defect in its critical backend check; one failure with586 passes/13 skips. Independent deterministic event-loop stall proved a retained-session/permit leak rather than an MMS regression. PR617 corrected bounded cancellation supervision after the caller deadline, retained lifecycle ownership and unknown-commit protection, and added seven stall/resistance cases. Owner and independent QA/Security each passed40 resilience cases. All six protected checks passed on68994349 in39681404056 before normal merge62619499. This actual main commit is integrated into the final MMS candidate; no weakened budget, removed assertion or blind retry. Final MMS integration CI and production acceptance remain separate gates.

Final integrationa8819654/run39682516190 passed five protected checks including both backend partitions and browser smoke, but the unchanged repair-order void-revision frontend test hit its default5000ms deadline (1825passed/1timeout). Independent review found no functional assertion failure: the capability-refresh test typed19 characters through whole-page controlled rerenders. Test-only click-and-paste entry retains the same reason, all three cases, real input/submission flow, all exact API/capability assertions and five-second limit; adds explicit value assertions. Owner before/after test phase1.93s/1.66s; independent3case pass1.73s, source GO. No production frontend change or blind same-head retry.
