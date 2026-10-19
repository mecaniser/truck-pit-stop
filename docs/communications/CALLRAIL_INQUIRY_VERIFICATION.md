# DB-COMMS-010: CallRail new-inquiry verification

Accountable owner: Backend & Integrations. Root owns integration and release; independent Security/QA must approve its own gate. [Contract](CALLRAIL_INQUIRY_CONTRACT.md) defines customer-free inquiries per receiving number, pinned manual replies, signed company routing and tenant isolation. All three new SMS routing, automation outbox and recovery flags stay false.

## Implementation and owner evidence

Frontend:43 communications tests, changed-source ESLint, TypeScript and production build pass. New-inquiry identity/filter, null customer, pinned sender,140-character limit, drafts and workflow controls are covered. Backend:69 focused provider/dispatch/inbox/messaging cases and96 adjacent identity/callback cases pass. Includes signed company routing, a shared tracker across numbers, foreign tenant/company/signing reference, unknown number, duplicate first messages, explicit customer-route precedence, no DBN/ETS guessing, manual idempotency, STOP, filtering and legacy endpoint isolation.

Owner migration rehearsal in a separate synthetic database: complete graph to183, existing customer/thread/message/route fixture,183-to184 retention and default-false intake; clean downgrade/reupgrade succeeds, downgrade with inquiry data refuses. Shared sandbox was not modified by this rehearsal. Independent review remains required.

Root operator artifacts are review-only by default. Fresh inventory contains16 active numbers across seven trackers, including ten website pool numbers; disabled empty tracker excluded. The rollout script makes GET-only provider calls, compares exact inventory and forwarding snapshots, validates source/schema/tenant/ownership/credential references and false flags, and changes only explicit binding intake settings. Hold retains existing conversations and works with disabled bindings or unavailable API credentials. Sorted binding locks match staff selection order. Independent source review passed after those two hold/lock corrections; runtime negative checks remain pending.

## Runtime preparation

The standard local controller was read and run; it refused the checkout's absent backend/.env/dirty active work. The approved isolated communications harness and existing configuration symlink are used instead. No production credentials were copied. Response-fix branch initially served frontend5186/API8006 from its exact process working directories; unrelated development services stayed intact. New-inquiry browser acceptance is not claimed until both processes move to this checkout.

Before the shared schema upgrade, root saved a mode0600 custom-format backup and stable fingerprints under ignored `output/callrail-inquiries/`. Schema183 counts:1694 tenants,1363 users,1995 customers,1344 threads,1399 SMS messages,559 CallRail bindings and523 routes. These are the accumulated isolated synthetic fixture database. Fingerprints exclude only newly added default columns so the upgrade can prove retained values unchanged. No schema upgrade or seed is implied by making the backup.

Independent migration GO, shared upgrade retention, signed-in desktop/mobile workflow, independent full Security/QA, protected CI and exact release/provider preservation evidence are still pending. Production numbers, forwarding and existing conversations are unchanged during implementation.

## Independent and browser acceptance

Independent Security/QA:40 provider/inquiry/dispatch cases and24 adversarial API/rollout cases passed on its own fresh full-chain PostgreSQL database. Independent migration rehearsal retained original affected columns and verified default false, SQL NULL/shape checks, uniqueness and refusal to downgrade nonempty inquiries. A bounded follow-up passed10 inquiry cases,24 independent negatives and21 inbox cases after correcting precise STOP reason preservation. No actionable finding remains in that reviewed scope.

Root applied the independently approved183-to184 migration to the backed-up shared sandbox. Every original row fingerprint/count in all seven checked tables matched after upgrade. Frontend PID25793 and API PID27267 serve this checkout at5186/8006, with frontend proxy and direct readiness200. Normal signed-in Alex Demo session rendered New inquiry, remote and receiving numbers, pinned sender and140-character composer. The branch badge and process working directories corroborate changed source. Source-aligned and browser-verified for the isolated environment only.

Actual local workflow: signed company incoming event created one customer-free inquiry; a staff reply went through the real adapter with a synthetic HTTP200 response, accepted immediately. Independent provider ledger shows exactly one HTTP invocation/status200; durable operation accepted/matched, attempt1, error null. Signed sent and received callbacks populated history. Replaying both incoming receipts returned duplicate and added no messages. Two receiving numbers with one shared tracker produced separate inquiries for the same remote phone. Existing Daniel customer history and route stayed intact; inquiry drafts survived switching to that customer and back. New inquiries filter, assignment to Jordan, resolve,140-character enforcement and STOP hold passed. STOP now states that replies are blocked, rather than a generic routing failure.

Mobile390x844: document scroll width390, pinned sender is read-only text, Send is visible; back-to-list and inquiry filtering work without overflow. Screenshots under ignored output/callrail-inquiries: desktop-reply.png, mobile-reply.png, mobile-list.png, mobile-stop.png. All original rows across the seven baseline tables still match after excluding only the explicit new test binding/thread records. Customer count unchanged; no Customer creation/merge or provider network occurred.

Final frontend44 tests passed; production TypeScript/build result is recorded before PR creation. The approved HTTP200/201 correction is included as a dependency on PR586 and must land first. Protected CI/current-main integration and exact production release remain gates. No production intake or forwarding changes have been applied.

Final production TypeScript/Vite build passed (3298 modules,10.43s bundle phase). Final44 frontend tests and diff check passed. Fresh backend restart on PID27267 and frontend-proxied readiness200 were followed by actual mobile rendering of the precise opt-out explanation; no provider invocation occurred during that hold check.
