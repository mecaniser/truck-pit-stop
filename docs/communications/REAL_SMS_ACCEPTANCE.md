# DB-COMMS-004 real SMS acceptance — deployment held

2026-10-16. Accountable owner: Backend & Integrations. Branch: `codex/sms-live-acceptance`.

User explicitly authorized the existing Twilio configuration and only their recipient ending0486, with receive/reply access confirmed. Credentials were read in memory from the existing backend configuration; no credentials were copied into the worktree. Existing sender ends3939.

## Evidence

- Independent pre-send safety review: GO; seven focused guard tests pass. Syntax compilation and diff whitespace checks pass.
- Fixed recipient authorization, immutable payload binding, durable SQLite single-call claim committed before network access, and no SDK retries.
- Isolated local PostgreSQL only; separate test tenant/customer. Normal local API remains simulated, and scheduled recovery remains disabled.
- Exactly one automated operation, attempt_count1, and one durable provider-call claim. Identical event enqueue/dispatch replay reused the operation without a second submission.
- Twilio accepted the API request; authenticated retrieval of that exact receipt returned `undelivered`, error30034. This is not successful handset delivery. The operation's `accepted` state records provider submission; delivery status is handled separately through the existing status projection.
- Read-only Messaging Service inspection: two services checked; the configured sender belongs to one service with an A2P campaign whose status is `FAILED`.
- No resend was attempted. The original one-call guard remains consumed.

Twilio documents30034 as a US10DLC number not associated with an approved campaign: https://www.twilio.com/docs/api/errors/30034 . Registration/campaign association must be resolved before a new controlled delivery attempt.

## Remaining gates

Handset delivery and reply are unverified because the outbound test was undelivered. Live signed callbacks into the new implementation are also unverified: this harness explicitly polls authenticated provider receipts and imports only the exact test-token reply into the isolated inbox. Existing production webhook routing was left unchanged.

Deployment and merge remain on hold. No campaign/registration, production configuration, or webhook settings were modified. Approval of this test does not authorize registration submissions or changes to the production sender configuration.
