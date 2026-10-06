# DB-036 dedicated VM coordinate import

Owner: Backend & Integrations. Status: In progress.

## Contract

Dedicated authenticated frontend route uses the existing API client and existing telemetry-snapshots POST. No new credentials, origin exceptions, provider activation, API schema, or database writes outside service.capture. Input source data is matched by exact unique VIN to the current fleet board; membership is derived from that record. A current active owner/admin and expected tenant are mandatory. Unknown source observation timestamps remain null; literal source age and source-read metadata are retained separately in evidence.

Validation previews the request without mutation. Unchanged coordinates and older observations are not resubmitted. A request checkpoint is saved before POST; uncertain results retain the exact request ID and payload. Success requires a server receipt; projection verification independently compares fleet-board snapshot ID and coordinates. A receipt is not proof of map rendering.

## Runtime preflight, 2026-10-06

Checkout vm-telemetry-import, branch codex/vm-telemetry-import, base 1f190835b5079d57a1ee03641bd100c0bc396b38. Ports 5173 and 8000 had no listeners. backend/.env and .dev-env are absent; approved local database configuration is unavailable. No secrets copied, database seeded/migrated, services replaced, or local backend pointed at production. Full-stack runtime is blocked; isolated synthetic frontend verification must be labeled as such.

## Guest diagnosis

Windows guest Computer Use can inspect the documented import form after window adjustment with URL safety checks intact. The www origin returned Not authenticated for both auth/me and fleet/board; the previously signed-in API origin is not in the trusted CORS origins (read-only preflight 400). No POST or credential extraction attempted. The fix is an app route using the existing authenticated client. Host collection schedules remain paused.

## Gates

Independent pre-implementation review of existing API: tenant/actor, unique VIN, membership, trusted cookie origin and replay are server-enforced. Caller must still implement unchanged/older guards and verify projection. Independent Security/QA review passed for supervised import after immutable baseline checks, GET-only verification after a receipt, and session/membership guards. Fourteen focused tests and scoped ESLint pass. Synthetic browser acceptance completed validation, simulated HTTP 201, persisted receipt and matching fleet-board readback at desktop and 390px widths. Receipt Blob contents and cleanup are tested; actual browser file download remains unverified because browser download observation timed out. No production receipt or fleet-map verification yet.

## Release and live acceptance still required

Other collectors must remain paused: client preflight cannot atomically exclude another backend writer between GET and POST. A changed baseline after an uncertain POST holds the checkpoint for reconciliation rather than minting another request. Deploy the reviewed frontend only with release authorization; recapture fresh source data in the VM, validate current identity/membership, import, retain the actual receipt, verify board projection and then the map pin. Fixture results do not establish authenticated production acceptance.
