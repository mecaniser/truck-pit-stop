# DB-036 location collection fallbacks

Owner: Backend & Integrations. High-risk worker change; no migration or public API change.

The location collector previously required a US ZIP-formatted address in a fixed
text position and a particular timestamp-status element before attempting to copy
coordinates. Read-only live probes confirmed valid city-only and named-place
locations were rejected, and one location lacked that timestamp element.

Acceptance:
- Each vehicle attempt uses a fresh page and verifies the observed vehicle link
  and exact VIN before and after collection; a changed/ambiguous VIN fails closed.
- One bounded fresh-page retry may recover missing UI fields. No fields are mixed
  between attempts.
- The visible location control provides Copy coordinates independently of the
  optional address label. Two matching coordinate reads are required.
- Unique status-owned tooltip text is retained even when normalization cannot
  establish an observation timestamp. Observation time remains unknown; source
  read time is separate. Conflicting tooltip/coordinate observations are rejected.
- Unknown-time coordinates may fill a first-ever position but cannot supersede
  any prior position. Same unknown coordinates do not refresh capture time.
- Tenant, actor, VIN, membership, source recency, and unchanged replay checks remain.
- Missing device/location controls preserve prior positions and remain unavailable.

Runtime preflight October 8: branch codex/motive-location-fallbacks based on
6f2947a7. Local 5173/PID77357 belongs to truck-health-popover; no backend8000 or
approved backend/.env exists here. Other runtime preserved. Isolated tests and
source-only Railway canary do not establish local fullstack readiness.

Source probes run in isolated DBN-motive-location-canary with no database
configuration, no schedule, and no imports. Private evidence stays outside Git.
Required gates: independent QA/security, protected CI, immutable deployment,
fresh dry run followed by receipt/replay/readback and retained schedule checks.
Rollback: restore the previous known-good location worker image; retain receipts,
existing positions and the hourly schedule. Trip and health workers are unaffected.
