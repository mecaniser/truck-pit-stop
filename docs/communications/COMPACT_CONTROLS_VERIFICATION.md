# DB-COMMS-025 — Compact Messages controls

Frontend & UX accountable, Fast UI lane; existing contracts unchanged.

Desktop dropdowns use 32px height, 5px/8px padding and a 6px icon gap, matching
quick-filter density. Explicit shell overrides prevent global density and focus
rules from restoring oversized controls or the double outline. Keyboard focus
uses a subtle border/background change; forced-colors uses a distinct border.
Mobile retains 40px targets. No labels wrap.

The existing sender label now sits beside Send SMS, stacking above the button on
mobile. Its value, unavailable/initiation states and routing logic are unchanged.
No consent, automation, send handler or draft persistence changes.

43 focused communications/ConnectedInbox/CustomerRepairContext tests pass;
changed-source ESLint, TypeScript and diff checks pass. Local signed-in desktop
and 390x844 browser verification: 32px measured dropdown, pointer/Escape focus
without outline/shadow, compact composer, original synthetic inquiry draft and
receiving-number route retained. No send or production mutation.

October 29 local runtime: branch codex/messages-compact-controls at f178a287 plus
scoped edits, frontend5193 PID16816/backend8013 PID16781 source cwd verified in
callrail-inline-mms/truck-pit-stop. Existing isolated communications_local_023_20261028
DB and Redis6386/db14 preserved; all three SMS flags forced false, external
provider network denied. Direct and proxied DB/Redis readiness pass; branch stamp
and edited rendering confirmed. Local URL http://127.0.0.1:5193/dashboard/messages
aligned and browser-verified. Screenshots /tmp/comms025-desktop.png and
/tmp/comms025-mobile.png are synthetic. New-shell CSS overrides reviewed against
the actual global rules; rendered sandbox uses legacy shell.

Merge, protected CI and production deployment pending.
