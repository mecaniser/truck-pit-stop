# DB-036 collector module independent review

Date: 2026-10-03. Reviewer: Architecture fallback, assigned by Product & Delivery.
Scope: root-owned `scripts/collect_motive_trips.mjs`, its test module, and
`scripts/motive_collector_state.mjs`. Reviewer did not implement or edit these
modules. The review excludes the reviewer-owned normalization, import wrapper,
and imported-bounds changes; those require separate independent gates.

## Verdict: GO for reviewed modules

The earlier false-completion issue is corrected: source row versions sharing
provider-link/departure identity prevent finalization, and neither scroll
stagnation nor loading establishes complete capture. Finalization requires a
matching independently observed count and matching source footer. It declares a
captured window, not a successful import or global history completeness.

Five source-collector tests pass under Node 22, covering overlapping pages,
missing tails, changed versions, date/filter/header mismatch, loading/empty
separation, expired sessions, and partial stagnation.

Independent real-filesystem checks also pass:

- State directory mode 0700 and checkpoint mode 0600.
- A second lock acquisition fails while the first is held.
- Checkpoint replacement preserves a readable complete JSON document.
- Parent-directory traversal in checkpoint names is rejected.
- Closing permits a subsequent lock acquisition.
- A preexisting nonprivate directory is rejected.

These checks used a disposable temporary directory and no production data.
Collector code only reads rendered DOM through the injected page and advances
visible scrolling. It does not obtain cookies, passwords, browser storage or
undocumented HTTP data. Driver/notes columns are excluded. Unexpected source
origin, report filter or table/timezone layout fails closed.

## Mandatory caller boundary

Company identity is deliberately not asserted by these modules. Product/Delivery
confirmed the daily caller must inspect the visible Motive company page before
and after capture, compare its company identity against the reviewed mapping,
and persist that account-check evidence privately. A mismatch or missing check
must prevent import/finalization as belonging to that company. This applies to
empty reports as well as populated reports. The runbook must retain that explicit
precondition; supplying a label in a JSON manifest alone is not verification.

Database tenant/VIN/membership authorization remains the importer's responsibility.
This module GO is not a deployment, schedule, current company-verification, or
production-import receipt. Authentication expiry and a stale lock require visible
operator recovery; no indefinite unattended-session guarantee is made.
