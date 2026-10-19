# DB-COMMS-009 CallRail manual inbox contract

Owner: Backend & Integrations. Architecture & API Contracts approved explicit per-thread binding. High-risk lane (tenant, external messaging, secrets, additive data).

Preserve MessageThread (unique tenant/customer), Twilio SID fields/callbacks, ETS identity/history, CallRail voice/text forwarding and all existing webhooks. Only mapped threads use CallRail; unbound threads retain Twilio. Map canonical DBN explicitly for the approved pilot, never infer from duplicate phone.

Number binding holds tenant/account/company/tracker/sender, enabled defaultfalse, environment credential references (no stored plaintext). Conversation binding pins thread/customer/phone. Provider receipts use new nullable provider/account/message/conversation/binding fields, never Twilio SID. Unique provider/account/message key and numeric aliases deduplicate sync/webhooks.

Existing send-operations API and Idempotency-Key remain the manual boundary. Operation snapshots bind sender/recipient/account/company/tracker via channelaccount identity and binding FK. Revalidate tenant/actor/optout/phone/binding before claiming dispatch; durable dispatching/attempt_count1 precedes provider IO. No provider POST retry on uncertain outcome. Response conversationid is not a message receipt. Accepted/sent is not delivered. A signed sent event may attach SCI receipt only with a unique exact bounded-time match; ambiguous events held durably.

Webhook endpoint selects trusted binding, verifies raw body base64HMAC-SHA1 Signature with company key, then checks company and localtrackingnumber. Unknown/ambiguous contacts are quarantined; no implicit customer create, accountcrossing or ETS reassignment. External CallRail staff messages are manual with unknown actor. Duplicate receipt locks plus uniqueness cover concurrent delivery. Existing forwarding is untouched.

UI conversation context adds sms_provider and sender_number; send_policy optionally max_length140. Server enforces CallRail140 independently. Existing otherproviders/channels keep1600; drafts not truncated. Sender/provider visible next to manual composer. No automation controls.

Official references: https://apidocs.callrail.com/#send-a-text-message and https://apidocs.callrail.com/#security . Send API permits manual person-to-person communication only, prohibits automated messaging. API201 top-levelid denotes conversation; individual receipt is webhookSCI/numericid. SMS_TENANT_ROUTING_ENABLED, SMS_AUTOMATION_OUTBOX_ENABLED, SMS_RECOVERY_ENABLED remainfalse.

Required acceptance: two tenants sharing a customer phone; canonicalDBN/ETSduplicate; signed wrongcompany/number/tamper/replay; webhook/send races and duplicate concurrency; binding/recipient/actor revoked afterintent; same idempotencykey replay/conflict; timeoutneverresent;141rejected; externalmanualingested; TwiliocallbackcannotmutateCallRail; automatedsourcecannotcallCallRail; forwarding unchanged. Run isolated before any live send. Real test limited to user ending0486; record handsetreceipt and exact inbound separately from APIacceptance.

Local runtime preflight: normal controller dryrun rejects absent backend.env; approved isolatedharness config referenced by symlink, no productioncredentials. frontendPID37144/5186 and APIPID37124/8006 both exactcheckout cwd, branchcodex/callrail-manual-inbox@aa9fbe24. PGcommunications_local loopback55460 revision181,Redis6386; direct/proxyreadinessOK. Explicit local overrides allthreeSMSflagsfalse. FrontendAPIorigin8006. Aligned but browser-unverified until featureacceptance. No foreignlistenersreplaced; no migrate/reseed duringinitialpreflight.

## Implementation and isolated acceptance

Migration182 upgrades the dedicated existing synthetic181database additively. No records reseeded or deleted. API restarted deliberately asPID41261 using `callrail_local_app:app`, exactcheckout backend, with allthreeflagsfalse and a network-free manualCallRail simulator. VitePID37144 still exactcheckoutfrontend, branch/SHAindicator aa9fbe24 with sourcechanges. Explicit syntheticDaniel binding added without customer/history changes.

29 focused PostgreSQL adapter/durable-operation tests pass. Independent Security/QA gate ran36 tests including7 extra challenges and closed providerfailure/HTTPsuccess race after finalSMS refresh+terminalstate preservation. Frontend33 tests, changed-sourceESLint, TypeScript and productionbuild pass.

Actual signed-in isolated browser: CallRail sendernumber and140counter visible; manualsend clearsdraft and becomesSent; realHMAC-signed localHTTP reply accepted, replay returns sameid, inboxpoll shows reply once. ExistingTwiliohistory remains in same thread.390x844 page scrollWidth390, Sendbottom720.5, senderwidth332; screenshots output/callrail-inbox/local-send-reply.png and local-mobile.png. Direct/proxyreadiness database/RedisOK. Runtime is aligned and browser-verified for this isolatedharness, not production.

ProtectedCI/merge/deployment, explicit productionbinding/secretrefs/webhookaddition, preservationreceipt and realinbox send/reply remain required. No productionprovider/configuration change made during implementation.

## Verified live read-only protocol correction

Existing CallRail registration and SMS pilot remain proven by the prior assessment. Fresh read-only API inspection of the user's own conversation shows current messages[].id is SCI-string (unlike the legacy numeric example) and message_type is used. Conversation spans historical numbers; current_tracker/current_tracking_number identify only its latestsender and cannot establish sender for oldmessages. Import now normalizes SCIidentity, honorsMMS, and holds unseenhistoricalrows unless individually allowed by an operator's verified_message_ids. Signed SCI callbacks need no optionalnumeric alias. Provider current_tracker_id may be null, documented as initialtracker current; only that null fallback is allowed, and currentnumber/company/recipient remain strict.

Only the two earlierCR-20261019-A pilotmessages may be explicitly imported, with provenance from the actual11:24am senderselection/sentconversation and confirmedhandsetreply: incomingSCI01a154c3b49177f2998b8f157f5e2c0b and outgoingSCI01a154c32bcb728e8dee273d7809e18a, providerconversationdhRSA. Do not import all7historicalrows as appnumbers. The earlier Websitepool history stays preserved atCallRail; no inferred sender is written. Independent finalprotocolreview32isolatedtests (25provider/dispatch+7challenges) GO, exacthashes inreviewreceipt.

Existing CallRail Webhooks integration2593909 has onlyELIS postcall/updatedcall receiver entries; textsent/received arrays empty. Release must append onlyDieselBridge textcallbacks and compare unchanged oldconfig/forwarding. Existing API/signingcredentialrefs have been securely staged inDieselBridgeWeb with --skip-deploys after provider signingkey equality check. No credential values saved incheckout/output, no deploytrigger, no livebinding or CallRailconfigchange yet.

## Staff manual sender selection

To avoid developer-only SQL routing after initial setup, existing authorized staff can explicitly select a connected tenant-owned CallRail sender for a known customer conversation, or restoreTwilio. PATCH `/communications/conversations/{id}/sender` accepts expected_version and nullablebinding_id, returns fullrefreshedconversation withaccount/version/policy. Context lists tenant-owned availableSMSsenders and selectedid; disabledcurrentbinding remainsselectedandblocked until explicitlychanged. Sharedthread lock, binding/phone ownership uniqueness and pending/unknown-operation guard prevent stalecompose, duplicateETSlinking and routearounduncertainsend. No customer/history/automatedtransport update. Draft preserved; UI waitsforresponsebeforeSend. Architecture approved this contract before backend/frontend split.

## Final preserved-route acceptance

Migration183 separates selected outbound sender from retained inbound routes. Switching CallRail A to B or back to Twilio keeps earlier number replies on the same canonical thread; it never deletes conversation bindings. Active thread/binding and binding/phone uniqueness remain enforced, with one selected sender per thread. Binding locks precede thread locks. Pending or uncertain operations block changes across the same recipient phone, including duplicate customer records.

Final combined PostgreSQL regressions:100 passed. Independent Security/QA:45 backend cases and30 focused frontend cases passed, including actual signed HTTP old-number replies, replay deduplication and STOP suppression after restoring Twilio. Independent183 upgrade rehearsal retained existing active/deleted row values; lossy downgrade refused safely. Frontend full communications suite39, changed-source lint, TypeScript and production build passed. Exact source hashes are in CALLRAIL_REVIEW.md.

Final signed-in isolated runtime: API PID51385/8006 and Vite PID45395/5186 belong to this worktree, synthetic PostgreSQL revision183, database/Redis ready, all three SMS flags false. Outbound manual send and signed reply appear once. After switching to Twilio, a signed reply to the earlier CallRail number remained on the original thread and replay returned the same message ID. Switching back preserved the CallRail draft and the pre-existing Twilio draft separately; only the newly created test draft was cleared. Mobile390x844 has scrollWidth390 and visible122px sender selector. Screenshots: output/callrail-inbox/local-preserved-routes.png and local-preserved-routes-mobile.png. Protected CI, release and live provider acceptance remain pending.
