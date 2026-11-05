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

## Live gate correction: bounded source-read recovery

The first canary completed21vitals captures, but truck70's Live read fell back to
its verified Summary, leaving the new engine-hours field null. Its older98hours
remained honestly projected; current authenticated Live showed104hours and a
matching VIN. Capture count alone was insufficient acceptance evidence.

Architecture approves one fresh-page retry for classified transient Live timeout
or transport errors, in the existing authenticated context and a fixed per-vehicle
budget. Each attempt retains exact Summary identity and Live provider/VIN checks.
Never retry credentials/imports, identity/session/route contradictions, ambiguity,
challenges, unknown errors or merely missing/malformed measurements. Wait for the
observed engine-hours label before capturing Live data. Dispose every page,
including late resources. After repeated transient failures, retain the last
verified Summary and original readtime, with unknown hours left null. A second
attempt failing before Summary must not erase a previously verified Summary.
Fresh tests and independent QA/Security must cover these boundaries before release.

## Canary correction: wait for authorized page readiness

The recovery canary stopped on its first vehicle before importing. Static logs
prove auth success and collection failure, but do not identify the exact exception.
Separate exact-source Chromium fixtures reproduce two legitimate loading states:
a Live click whose hash changes50ms later, and a blank VIN cell filled50ms later.
Both were rejected prematurely. The baseline fixture with immediate readiness works.

Architecture permits a wait within the same existing deadline, not another retry.
Only the exact verified starting Summary URL is transitional; it must resolve to
the expected provider Live route. Wrong providers, origins, paths, auth/challenges,
nonempty different or malformed VINs and duplicate VINs remain immediately fatal.
Missing table or blank/missing loading VIN may remain pending until exactly one
expected VIN is rendered. Run source-auth checks during readiness polling. Bound
VIN-less reads retain their separate reviewed-absence contract. Pending timeout may
use existing bounded transient read recovery with honest original-time Summary.

After every Live route/VIN/challenge guard succeeds, two null Live measurements
must not discard an available verified Summary odometer. Return that Summary with
its original source readtime. Do not retry, merge different-time fields or refresh
the timestamp merely for unavailable values. Any present Live value, including
zero, retains the existing Live partial result. Static read-stage/failure categories
may be logged; URLs, VINs, auth values and challenge tokens remain private.

The actual field-bearing Summary snapshot must itself satisfy pure summaryIdentity;
matching surrounding reads cannot authorize a contradictory middle snapshot.
Validate before promoting its values in VIN and reviewed-absence paths. The same
both-null fallback applies to bound vitals only after fresh post-Live absence and
identity proof. Positive/zero partial Live values remain unmerged.


## Password-form readiness and diagnostic contract

The PR783 canary failed before the password-submission phase. Its generic
ambiguity category cannot establish whether initial loading, duplicate controls
or post-fill validation failed. Independent offline probes reproduce both loading
and contradictory forms; no production cause is asserted.

Permit waiting only before password entry, on the exact trusted password route,
for a demonstrably empty document: no forms, inputs (including hidden inputs),
editable controls, buttons or iframes, no rendered body text or other rendered
content. The wait consumes the original 15-second fallback budget, uses the same
page/context, and performs no navigation or credential retry. Lookup validation
remains immediate and strict. Any nonempty/partial state proceeds to the existing
strict review and fails for contradictions, duplicates, challenges, wrong account
or unsafe form destination. Review again after password fill and verify the
password input still contains the supplied value before the single submission;
never refill or retry if the form changed.

Expose only fixed validation-phase and guard enums through the existing failure
event. Never serialize URLs, account values, field values, DOM or provider tokens.
Independent QA/Security must prove blank-to-ready success, blank timeout, blank
to contradiction, post-fill mutation, one-fill/one-submit limits, unchanged
context count, strict destination/account checks and diagnostics privacy. New
source/receipt/projection parity and natural scheduled execution remain release
gates; prior-image success is historical evidence only.


## Native form ownership and observed auxiliary forms

The next scheduled attempt failed at lookup revalidation with the fixed
`credential_count` guard, before lookup submission or collection. Direct
inspection of the official rendered lookup document showed three global generic
email inputs but only one owned by the selected native login form. Two additional
CSS-hidden email fields belonged to separate unselected forms. An offline real
Chromium fixture reproduces the existing helper's rejection and proves that the
native POST includes only its own email field. Global document counts therefore
misclassify the observed official page.

A single public lookup using a synthetic reserved-domain identifier (no real
account identifier and no password entry/submission) established the password
page structure too. Its selected native POST form owns one password and one
hidden matching legacy account field, with no generic email field. A separate
optional SSO form and the same two hidden auxiliary forms explain three global
generic email fields. No auxiliary/SSO/metadata values were inspected.

Architecture and Security approve replacing global hidden-field totals with
actual native `element.form` ownership, including off-form associated controls.
Global visible-field uniqueness and visible challenge checks remain unchanged.
The selected native input, hidden account and submitter must actually belong to
the one approved native POST form; association/submitter overrides and duplicate
owned credentials remain fatal. Preserve exact action/method/target, matching
account, post-fill password-value, one-fill/one-submit and15-second deadline
checks before entry and again before submission. Never select another flow if
the native password form is absent.

Permit at most two distinct unselected auxiliary ancestor forms only when each
matches the full observed seven-control profile: `firstName` and `lastName` text
inputs, one `email` email input, `address` and `comments` textareas, and two unnamed
native submit buttons. Every control must be CSS-hidden, actually owned by that
form, and free of form-association, autocomplete and submitter overrides; the
auxiliary form has no action, method or target attributes. No missing/extra or
rebound control is accepted. These hidden ordinary textareas are not an active
challenge; visible textareas/selects/iframes/OTP/password controls remain guarded.
Never read, fill or submit an auxiliary form.

At the password stage only, permit at most one unselected optional SSO form with
exact effective HTTPS `auth.gomotive.com/login/sso`, POST/self, no query/hash or
user-info, one owned hidden generic email field, three noncredential hidden
metadata inputs and one correctly owned visible exact `Log in with SSO` native
submitter. Reject overrides, unexpected credential/OTP/account/editable fields,
extra submitters, duplicate SSO forms or unsafe destinations. Never read its
email/metadata values, fill it or submit it. The actual native password form must
independently satisfy every existing credential and destination check. An active
SSO redirect or challenge remains terminal.

Revalidate this complete classification after fill. Positive fixtures must model
the full observed structures and late auxiliary insertion; negative fixtures must
cover altered/third/visible auxiliary forms, native and off-form duplicates,
wrong SSO destination/method/target/ownership/overrides, metadata/credential
substitution and native-form absence. Independent QA/Security and fresh exact
runtime/source/receipt/projection/scheduled acceptance remain required.


## Observational outer-identity substages

The earlier manual canary exhausted the unchanged outer VIN reader before vitals;
its timeout category could not identify which await failed. Architecture/Security
approved a backward-compatible optional `onStage` callback for this internal
reader. It emits only fixed page-creation, Summary-navigation, Live-link, optional
VIN-wait, route-check, body-read and cleanup stages. No additional DOM/network
reads, awaits, navigation, retries or timeout changes are permitted. Existing
callers without the option retain their behavior.

Error metadata uses a private WeakMap, with fixed stage and coarse route enums
from synchronous `page.url()` only. Never retain/serialize URLs, hrefs, IDs, page
content or field/error values. Metadata and observer failures must not replace
source errors, including frozen/non-Error throws. Preserve existing foreign-timeout
conversion, swallowed optional VIN wait, three transient attempts and cleanup
precedence. Successful cleanup cannot relabel a primary failure; an overriding
cleanup failure still overrides as before and is identified as cleanup.

Tests cover each await, default callers, callback errors/rejections, source and
metadata failures, cleanup outcomes, privacy and unchanged retries/timeouts.
Independent combined gates remain required.
