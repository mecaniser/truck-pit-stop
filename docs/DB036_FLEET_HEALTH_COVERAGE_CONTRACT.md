# DB-036 fleet health coverage and scheduled recovery

Backend & Integrations accountable. Independent Architecture reviewed the bound
vitals contract on2026-11-04 before implementation. No schema/public API or fleet
relationship changes. Preserve the default77Cargo scope and reviewed609 exception.

All source vehicle discovery must use complete rendered directory evidence under
the verified source account and timezone. Compare Admin Vehicles and Health by
exact provider/VIN or an existing reviewed binding. Unit labels are presentation,
never identity authority. Do not append supplemental Admin rows to Health while
claiming its original directory count. Source absence and unavailable readings are
separate from mapping/import failure.

For reviewed VIN-less26, collect identity before and after summary/Live vitals.
Require an explicitly allowlisted company/provider pair and stable exact provider,
loaded profile/unit/route and VIN absence state. Live must reject genuine,
malformed or contradictory VIN evidence. Keep vin=null and use the existing
database-reviewed dashboard binding; never pretend the placeholder is a VIN.

Resolve bindings through the existing tenant/company/provider/customer/source-time
contract. Use BoundTelemetryCapture with binding ID, company ID, source-read time
and source absence state. Its evidence must include sourceReadTime (camelCase),
company_id and absence state because current projection revalidates that evidence.
Keep existing VIN-path evidence/digests and legacy receipt identities unchanged.
Fault diagnostics still require a real VIN; bound26 faults remain unavailable.

Dry run, atomic commit, unchanged replay and exact readback remain mandatory.
Missing/invalid binding may exclude an initial row with a specific reason; an
eligible request losing its authority during commit/recovery must fail rather
than silently disappearing. Successful bound matches cannot be labeled absent.
Readback must verify actual current Fleet projection as well as saved identity.

Login remediation must follow rendered official auth controls, bounded by the
existing timeout and origin checks. No private endpoints/session extraction,
credential logging, SSO/MFA bypass, permission changes or blind import retries.
Record the observed source form contract before changing authentication behavior.

Acceptance requires focused negative tests, independent QA/Security, exact deployed
source, complete source/receipt/per-truck readback, preserved canonical mileage and
business identity, production display checks, and a successful scheduled execution.
A manually triggered canary alone does not prove automatic recovery. No unavailable
source measurement is invented or borrowed from a service odometer.

## Official lookup/password recovery

Architecture approved health-only opt-in recovery after both anonymous contexts
end in the exact legacy redirect loop, before any credential submission. All
other errors remain terminal; callers without configured opt-in are unchanged.
The public rendered lookup form was inspected on2026-11-04: HTTPS
`auth.gomotive.com/login/lookup`, one email input and Continue in a native POST
form targeting exactly `/login/authenticate`. The password document uses the same
native POST target with a hidden matching email and one password input/Log in.
Preserve provider CSRF and hidden fields in the native form; never reconstruct a
private request. Validate exact origin/path, effective native form action (including document baseURI), method/target, input types,
unique associated submitter and no submitter override attributes, including empty ones before each credential
fill and again before submission. Reject foreign origins, wrong accounts, SSO,
MFA/challenges and ambiguous or altered forms without retrying credentials.
Reject additional visible form inputs or challenge controls before credential entry.
A single15-second inclusive deadline covers completed disposal of both anonymous
contexts, new context creation and both submissions through app redirect;
late resources are disposed. Diagnostics expose static stages/categories only.

## Source availability audit

The verified source account KT8934277 showed23of23 active Admin vehicles and one
of one deactivated vehicle. Trucks24 and42 were absent from both lists. Trucks5
and532 had blank odometer and engine hours in their exact Live views (Summary
reported zero devices). Truck26 had548550.82mi and21109h with no displayed VIN;
it must use its existing reviewed binding. Thus21of25 local active memberships
have both readings available in this account. This is source availability proof,
not proof of successful scheduled ingestion; the latter remains a release gate.
