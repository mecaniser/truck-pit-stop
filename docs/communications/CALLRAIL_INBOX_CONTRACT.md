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
