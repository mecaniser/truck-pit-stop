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

At the pre-release checkpoint, no restoration had been executed. Do not send an outbound message, import unrelated history, fetch the attachment, enable SMS flags, or alter CallRail webhooks/forwarding as part of recovery. The attachment remains viewable in CallRail.

## Prerequisite CI correction

Candidate663c0621 exposed an existing error-persistence hard-deadline cleanup defect in its critical backend check; one failure with586 passes/13 skips. Independent deterministic event-loop stall proved a retained-session/permit leak rather than an MMS regression. PR617 corrected bounded cancellation supervision after the caller deadline, retained lifecycle ownership and unknown-commit protection, and added seven stall/resistance cases. Owner and independent QA/Security each passed40 resilience cases. All six protected checks passed on68994349 in39681404056 before normal merge62619499. This actual main commit is integrated into the final MMS candidate; no weakened budget, removed assertion or blind retry. Final MMS integration CI and production acceptance remain separate gates.

Final integrationa8819654/run39682516190 passed five protected checks including both backend partitions and browser smoke, but the unchanged repair-order void-revision frontend test hit its default5000ms deadline (1825passed/1timeout). Independent review found no functional assertion failure: the capability-refresh test typed19 characters through whole-page controlled rerenders. Test-only click-and-paste entry retains the same reason, all three cases, real input/submission flow, all exact API/capability assertions and five-second limit; adds explicit value assertions. Owner before/after test phase1.93s/1.66s; independent3case pass1.73s, source GO. No production frontend change or blind same-head retry.

Candidate6491427d/run39683976465 again passed both backend checks, build, browser smoke and migration, but remaining frontend174files passed/2failed: inquiry-filter workflow5s deadline and force-void initial-loading query1s deadline. Earlier void-revision case passed. Focused test-only corrections wait for the actual QueryClient fixture to settle under default waitFor and scope repeated accessible-name queries to existing conversation/list regions. Invoice-action label lookup retains button-role assertion. Owner38cases pass5.30s; independent38cases pass5.39s and QA/Security GO. No removed case/assertion, synthetic loading bypass, timeout increase, CI configuration or production frontend change. Local baseline passed, so no deterministic local timeout or aggregate inbox speedup claim.

## Merge and deployment block: 2026-10-21

PR615 merged normally as `e3f0f4c83cdf111920713f0c199005e400a39785`. Final head `f31a35d6d3f2643e76341c2547b8c3edbfdbc5f5` passed all six protected checks and dependency preparation in run39685540989, no bypass or same-head retry. Checked and merged trees both `d4ea9606792ff7fa01ed4dd1d5f5aa702399348b`. The final frontend remaining partition passed all176files/1826tests. The original MMS implementation is byte-identical to its independent source review.

At22:27UTC, explicit connected-source exact-commit deployment requests for both Web and Worker returned `Deploys have been paused temporarily`; authoritative deployment lists contain no new e3f0f4c8 deployment. API still serves `f3b1cfa4610afffadc91a067c12d31180c3cd619`, DB/Redis readiness passes. Last successful Web deployment `76636761-434d-4a38-b114-3f46f9de9792` and Worker `c52e4e04-7c1b-44b4-b2d2-2f3a168bb4e4` use f3b1cfa4. Three SMS rollout variables remain unset/defaultfalse on both services; no variable writes.

The official [Railway incident](https://status.railway.com/incident/QH8L8B3E) confirms a platform-wide deployment pause. Railway also published a [security disclosure](https://blog.railway.com/p/security-disclosure-wednesday-october-21st) recommending rotation of stored environment credentials after possible exposure. The user was informed; no account-specific compromise conclusion, credential rotation, provider change or unrelated security mutation is claimed or performed by this release.

The original reported inbound receipt remains in quarantine with no resolution. No production recovery, media fetch, outbound message, callback/forwarding change or customer-identity merge has occurred. Pre-release read-only baseline:199SMS/14threads/775customers/3CallRail conversations/16bindings/0reply routes/4sendoperations/schema187. Private aggregate row hashes support retention checks without publishing customer data.

Remaining acceptance: Railway recovery; exact successful application deployments without rollback of newer authorized source; served SHA/readiness/retention/false flags; reviewed read-only preview and fingerprint-bound one-receipt recovery preserving quarantine history; authenticated4:10PM receipt/derived reply-number UI. A resumed existing15-minute release follow-up carries this authorized scope and pauses on completion. No Done claim until those gates pass.


## Production release and acceptance: 2026-10-22

Owner: Backend & Integrations; Release & Reliability executed the authorized release. Earlier blocked states above are historical.

- Source/merge: freshly confirmed PR615 merged as `e3f0f4c83cdf111920713f0c199005e400a39785`, protected run39685540989 successful on `f31a35d6d3f2643e76341c2547b8c3edbfdbc5f5`. Refreshed main `65afe9b8fa52a946ca86f645abbf4ebe70aa3604` differs only in the board and this contract; no newer application code was rolled back. Frozen suites were not rerun.
- Deployment: actual authenticated Railway workspace no longer showed the prior Limited Access pause. Explicit exact-source deployment requests were accepted once per service. Web `3598d6a6-814d-489a-b1f2-5be2fed2a2e1` and Worker `2fcd0a16-0c3a-4ef7-8161-c141128e2a38` both reached SUCCESS on exact e3f0f4c8. API and website `/build-version` both report that full SHA; build stamp `2026-10-22T16:58:01.810Z`. DB/Redis readiness passed.
- Flags/runtime: all effective `SMS_TENANT_ROUTING_ENABLED`, `SMS_AUTOMATION_OUTBOX_ENABLED`, and `SMS_RECOVERY_ENABLED` remain unset/defaultfalse on both services. No configuration writes. Schema remains `187_labor_twilio_merge`. No local browser alignment claim is made; acceptance used the authenticated production inbox.
- Retention: pre-recovery SMS199/threads14/CallRail conversations3/bindings16/routes0/sendoperations4 matched the prior aggregate hashes. Customers increased775 to776; three customer rows show the same scheduled Easy Truck Shop import update at `2026-10-22T02:16:15.435408Z`. A fresh immediate baseline preserved that activity. Post-recovery customers, bindings, reply routes and send operations match that fresh baseline exactly.
- Recovery: reviewed command ran from clean exact deployed source. Read-only preview matched only the original unresolved empty-caption inbound MMS and original October21 16:10:13.068 EDT timestamp. Fingerprint-bound apply committed one receipt through current `apply_event`, with all existing intake/tenant/identity checks active. Same-transaction duplicate replay preserved unread count; pre-existing SMS and unrelated threads remained unchanged; original payload/hash/reason retained with audited resolution. A separate repeat returned already-restored/no_write. Private identifiers and proof remain outside the repository.
- Concurrent live traffic: a separate ordinary inbound SMS at `2026-10-22T16:56:49.031Z` was also retained. Final counts201SMS/16threads/776customers/5CallRail conversations/16bindings/0reply routes/4sendoperations therefore include one recovered receipt plus that separate live receipt, not two recovery writes.
- Signed-in acceptance: Messages showed the restored inquiry at4:10PM on Wednesday October21 with `[Attachment received in CallRail. Open CallRail to view.]`. Reply number was automatically derived from the original receiving binding with no sender chooser; all five pre-existing visible conversations remained alongside the restored inquiry and new live inquiry. Draft was empty before reload, no message sent, no consent/service-update/assignment/resolution setting changed. Opening the restored thread naturally marked it read. Private screenshot retained outside the repository.
- Boundaries: no media retrieval, native image rendering, provider/callback/forwarding or credential change, identity merge, route seeding or automation enablement. Legacy immediate notifications remain unchanged. DB-COMMS-016 acceptance is complete; existing release heartbeat can be paused.
