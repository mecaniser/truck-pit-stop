# DB-COMMS-023 implementation verification

October 28, 2026 America/New_York (October 29 UTC).
Accountable: Backend & Integrations. Branch: `codex/messages-contact-repairs`.
Status: implementation and local acceptance passed; [PR665](https://github.com/mecaniser/truck-pit-stop/pull/665) open, protected CI/release pending.
Latest main `3b7f3519` documentation integrated; reviewed application fingerprints unchanged.
[Contract](CONTACT_REPAIR_CONTEXT_CONTRACT.md) defines the shipping boundary.

## Implementation

Separate conversation/customer/contact associations preserve inquiry transport
identity. Explicit contact/repair links drive contact history and serviced trucks.
Fleet history is a separate scope. Staff can select an existing person, add a
non-primary person to a customer, or atomically create a customer/person and link
an inquiry. No phone-based merge or historical inference. Repair links are
explicit; removal is outside v1.

Mutations use tenant-scoped access, version checks, durable idempotency and row
locks. Unknown save outcomes retain the original payload/version/key in scoped
session storage. Retry does not create a new request. Messaging fields, routing,
consent, provider credentials and automation settings are not mutated.

## Automated and independent checks

- Backend: 60 passed: 15 context tests plus 45 existing identity/MMS receipt
  regressions. Includes real PostgreSQL concurrent same-key creation, separate
  actor/thread email race, atomic rollback and inquiry identity preservation.
- Frontend: all communications tests, 71 passed across eight files; TypeScript
  `--noEmit` and changed-source ESLint passed with zero warnings.
- Independent QA/Security reviewer `context_independent_gate`: GO; independently
  ran 15 backend and eight frontend cases plus six additional HTTP, relationship,
  read-purity and uncertain-retry probes. Both found retry defects were fixed and
  independently reproduced as passing before GO.
- Gate endpoint SHA256:
  `41b391923e6155acfa7ebe1525ce8fa28b91a65974e8e9c9006002ec2fdc391d`.
- Gate sidebar SHA256:
  `272a080a523512361395299199fff98028762cd22645eecb8970293fde9653ed`.

The dedicated PostgreSQL cases are opt-in isolated-local tests; ordinary CI runs
the schema cases and existing suites. Local integration evidence is separate
from protected CI. No tests were waived or default timeouts increased.

## Migration and retention

Migration `190_messages_contact_context` from `189_trip_reviewed_binding` adds
three association/idempotency tables, with no backfill or existing-row updates.
Rehearsed against the dedicated synthetic PostgreSQL database. All nine existing
table counts and full-row digests matched before/after migration: SMS, threads,
customers, contacts, vehicles, orders, CallRail mappings/bindings and send
operations. Following browser actions, the original fixture rows in all nine
tables still matched; only explicitly created CRM records/associations were added.
Send operations remained zero.

## Local runtime and browser acceptance

Worktree `callrail-inline-mms/truck-pit-stop`, branch `codex/messages-contact-repairs`.
Frontend `http://127.0.0.1:5193`, PID7804; backend8013, PID12079 at acceptance.
Both process working directories match the implementation worktree. The frontend
proxy reaches backend readiness, database/Redis both OK. Dedicated synthetic
PostgreSQL `communications_local_023_20261028` on loopback55460; Redis6386/db14.
All three SMS rollout flags false. External HTTP and Twilio calls denied in the
local launcher. No production credentials, mutations or sends.

Signed-in synthetic owner browser verified:

- Existing customer/person link on an inquiry, with original message and reply
  number unchanged and unsent draft intact.
- Explicit current and completed repair links: contact scope shows only those
  two repairs and one serviced truck; fleet scope shows four repairs/two trucks.
- Active/history/all grouping and separate fleet scope.
- Repair deep link opens the selected order. Browser Back restores the inquiry
  and its unsent draft.
- Add customer creates the company/person and links the inquiry atomically;
  the inquiry identity and receiving-number reply route remain unchanged.
- Compact390x844 drawer displays repair links/status/truck history with usable
  scrolling. Default desktop viewport restored afterward.

Private synthetic screenshots: `/tmp/comms023-desktop.png` and
`/tmp/comms023-mobile.png`. Runtime is aligned and browser-verified for this
implementation. Local evidence is not deployment evidence.

## Release boundary and rollback

Production deployment is verified below. No production customer linkage has
been performed for acceptance. Live save acceptance requires an identified
customer/person/repair match, not unsolicited test writes to real contacts.

On a release regression, stop new CRM linking and roll back only this application
change while preserving newer authorized ancestry. Leave additive tables and
recorded links intact for investigation; do not downgrade away customer links or
rewrite SMS history. Never enable automation as part of rollout or rollback.

## Authorized release — October 29, 2026

User authorized merge, deployment and live verification with automation off.
Integrated latest main `157a036a` (new fleet fix) without changing Messages source.
All six strict protected checks plus dependency preparation passed on
`4b31b09317fa47fbf25fb84f47a854be14a4b7df`, run40817602707.
PR665 merged as `004a49b4bdb23659301df54ff1e5228042f2db1f`; checked and
merged trees both `a4556d8364b86c4c7f584c1ab60a9203a8b975ea`.
Automatic Railway Web `4653d6be-6766-42de-987b-ca6a6ccc4e9c` and Worker
`d940b860-e650-45ff-bae8-017ef95004a0` started for that exact source.
No duplicate deployment requested. Both deployments SUCCESS; API and website
serve the full merge SHA, build2026-10-29T04:35:41.743Z. DB/Redis readiness pass.
Migration190 is applied. All nine baseline table counts and full-row digests
remain unchanged; all three new context tables are empty. All three SMS flags
remain unset/defaultfalse on both services.

Read-only pre-release baseline:214 SMS,22 threads,799 customers,596 contacts,
1516 vehicles,3843 repairs,11 CallRail mappings,16 bindings,5 send operations;
schema189. Private row-digest baseline outside repository. All three rollout
flags confirmed unset/defaultfalse on Web and Worker. Real customer/contact/repair
associations require an identified match; user was asked which records to use.

### Live authenticated acceptance

- Customer linking dialog loads existing customer/person choices and explicit
  confirmation; canceled without saving an association.
- Contact scope correctly requires an explicit person link; fleet repairs and
  trucks load separately from the existing customer association.
- A fleet repair deep link opens the exact selected repair order. Browser Back
  restores conversation selection, unsent draft and the original reply number.
- Temporary verification draft removed; original empty draft restored and Send
  disabled. No sends, consent changes, assignments or customer mutations.
- Private screenshot: `/tmp/comms023-live-sidebar.png` (outside repository).

Deployment and read-only live journeys pass. Production customer/link save and
contact-linked repair population remain pending the user-identified real match.
Local synthetic create/link acceptance already passed; do not substitute it for
a production save claim. Item remains acceptance pending, not Done.

### Authorized live linkage completion — October 29, 2026

User saved the customer/person association, then explicitly authorized all repairs
for two named DBN trucks. Through the authenticated UI,16 existing fleet repairs
were confirmed individually and verified in Contact / History, including the
historical cancelled repair. Both serviced trucks appear. Fleet history remains
separate. Original reply route and empty draft unchanged; no SMS sent.

Read-only comparison after linking: all nine baseline tables remain byte-digest
unchanged. Additive tables contain1 customer/contact link,16 repair links and17
mutation receipts. All three SMS flags remain unset/defaultfalse on Web/Worker.
Private screenshot `/tmp/comms023-sergio-linked-history.png` stays outside Git.
This supersedes the earlier acceptance-pending note; DB-COMMS-023 is Done.
