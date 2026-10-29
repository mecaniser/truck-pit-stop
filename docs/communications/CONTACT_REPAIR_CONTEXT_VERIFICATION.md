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

No production deployment or customer linkage has occurred for this item.
Protected checks must pass on the final PR head; merge/deployment need release
authority. Verify additive migration, exact served source, unchanged routing and
false SMS flags at release. Live acceptance must use authorized customer actions,
not unsolicited test writes to real contacts.

On a release regression, stop new CRM linking and roll back only this application
change while preserving newer authorized ancestry. Leave additive tables and
recorded links intact for investigation; do not downgrade away customer links or
rewrite SMS history. Never enable automation as part of rollout or rollback.
