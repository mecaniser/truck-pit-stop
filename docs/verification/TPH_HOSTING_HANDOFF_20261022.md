# Trucks Parking Hub Mac hosting handoff — October 22, 2026

Owner: Release & Reliability. Scope: existing isolated application hosting, separate from production failover and the unfinished 24-hour infrastructure observation.

## Acceptance

A running dedicated Mac server, enabled HTTPS hosting, reachable protected TPH website, rendered application homepage and sign-in page, exact accepted application source and healthy isolated services. Railway, production domains and live switching remain untouched. Real payments, messages, scheduled jobs and provider access remain disabled. Existing recovery and rollback journals are preserved; no redeployment or restart is needed merely to hand over a working application.

## Verified runtime

At October 22, 2026, approximately 4:58 PM America/New_York, the deployed TPH source is `b369e9f5e28584ba99f1cbe35d8f65080a51aeda`, image `sha256:95df264063f3224f9a2519fd68a99e537f7a8da26d17ff78b5e6a87267a798b0`, running on `sergio@192.168.4.239` in the existing `tph-local-test` stack. Controller readiness, served source, configuration, identity and baseline comparisons pass; deployment and recovery uncertainty flags are false.

User address: https://tph-test.elisprotech.com/ . The browser validated ordinary HTTPS, passed the existing private test gate using the existing credential without printing it, and rendered the hydrated homepage headed “Your lot. Your rates. More trucks.” The native sign-in page displayed “Choose your access.” and driver/fleet, property-owner and team-access options. No real registration, provider login, booking, payment or message was submitted. This pass verifies the sign-in screen, not a fresh native authenticated account journey. The homepage remains open in the user's in-app browser.

[Current browser screenshot](mac-test-public/tph-hosting-handoff-20261022.png).

Independent Security (`merge_safety_review`) directly verified five running services, healthy configured healthchecks, no OOM/privilege/socket exposure, internal application/worker/database/identity networking, and gateway bindings only on loopback18201/18211. LOCAL_TEST_ONLY and DISABLE_SCHEDULER are true; Square uses sandbox with invalid fixture credentials. Monthly autopay/subscriptions, blog publication, WorkOS and listed SMS flags are false. Pending jobs0, total synthetic jobs1, published0 and scheduled0. Unauthorized public requests deny. Scoped GO covers the existing isolated hosting handoff only.

Independent QA (`continuity_independent_gate`) separately verified controller/source/image, trusted HTTPS, unauthenticated gate denial, existing-credential authentication with a secure host cookie, homepage/sign-in HTML200 and three real same-origin JavaScript assets200. No availability blocker was found. Browser rendering evidence remains the owner pass above; independent QA did not claim a second browser execution. Scoped HTTP/runtime GO.

## Deploy a chosen committed branch

The existing workstation entry point is available and its help was checked:

```sh
~/.local/bin/deploy-tph YOUR_LOCAL_BRANCH
```

It reads committed source from `~/GitHub/TPH`; use `--repo /absolute/path` for another intended checkout. It builds and deploys only the selected Mac test web service under the reviewed controller. It does not push Git, merge, call Railway, enable workers or change DNS. No fresh branch was selected by this request, so the healthy accepted pinned release was retained.

```sh
~/.local/bin/mac-test status
~/.local/bin/mac-test rollback tph
```

Rollback requires a previous accepted release. TPH currently has no previous accepted deployment; the first future successful update will retain today's accepted release for rollback. The command does not roll back database contents, migrate or reseed. See `deploy/mac-test-deploy/README.md` in the owned mac-test-deploy worktree for the full reviewed contract.

## Limits

The current site contains synthetic data behind the test access gate. It is the actual TPH application running on the Mac, but is not the production booking authority. It is not a claim that the latest moving main has been deployed. Zero-loss live failover remains blocked on its distinct data, fencing, provider reconciliation and final release gates. The original failed observation and the new active observation are preserved. The active window continues in the background through October23 at3:28:23PM Eastern; it does not block use of this existing test website.

No application deployment/restart, Railway change, production-domain switch, recovery-helper replay, new monitor, real provider action, source push or CI run occurred during this handoff verification.
