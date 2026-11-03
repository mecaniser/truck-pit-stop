# PR764 release gate returned

Exact reviewed head:711c136c94ee26fd52a6b643b778b9de853ea470. Base:8582077ba3069e1e1ddbf1dd2d934d7ff80ca58a. PR remains open, draft and unmerged. No production deployment or formal PR review approval.

Independent source/probes initially supported the cross-tab client fix. Two additional owner probes fail on untouched base2/2 and pass at the candidate2/2: a warm peer remains authenticated after shared logout, and passive old profile/token writes overwrite the ended projection before the storage event. This is a store-level reproduction, not a fresh real-browser claim.

## Blocking overlap regression

1. A completes the real WorkOS login/callback routes.
2. A's real WorkOS logout handler executes; hold only its outgoing response headers.
3. B completes login/callback in the same HTTP cookie jar before A's response arrives.
4. B's authenticated cookie-user endpoint returns200.
5. Release A's previously generated logout response.
6. B's cookie-user read returns401; refresh returns401; its valid opaque server session still exists. Both access_token and workos_session cookies are absent.

Executed through the actual FastAPI ASGI app, SQLite/FakeRedis test fixtures, a controlled WorkOS exchange and a standard httpx cookie jar. No production credentials, live provider or browser was involved. This reproduces application-response ordering and cookie loss, not a live-provider interaction. Independent extracted-endpoint/RFC-cookie-jar probe corroborates it. The logout endpoint is byte-identical to base: inherited cookie behavior is newly exposed by the peer projection allowing B login during A's pending logout. Client epochs cannot stop the browser applying old Set-Cookie deletion headers.

Artifacts:workos-overlap-real-asgi.json/.log; independent-late-logout-cookie-order.py; late-logout-cookie-order.log; INDEPENDENT_SECURITY_QA_711c136c.md. The executable failing regression is appended to owner-probe-711/backend/tests/test_workos_auth.py. Desired final assertion remains B's cookie-user endpoint200; it currently fails401. No assertion was weakened.

Existing authored browser cases release A before B login. They do not test this ordering. Correction must preserve actual logout revocation and HttpOnly/cookie/tenant protections while preventing prior response completion from terminating the replacement session. Test both old response and old request completion after B, cross-tab and Back/reload, plus failed/abandoned logout and stale completion hints. Do not solve by weakening revocation or ignoring401s. Revised protocol/coordination needs fresh independent security and genuine browser acceptance before release.

## Other evidence and limits

Hosted exact-head41677209681 has all7 jobs green: backend599critical+4742remaining=5341pass,13+455=468skip; frontend218critical+2314remaining=2532pass;5smoke. Owner separate full backend5341pass/468skip/0failures. Build/lint pass. Owner first frontend2531pass/1Fleet delayed-profile timeout5s; focused6/6 pass (including2693ms newcase), independent6/6 pass; no deterministic async deadlock found. Full clean repeat after backend passes2532/2532 across232files in161.13s, zero unhandled errors; no assertion or timeout changes. The earlier single timeout is recorded and not treated as a clean first run.

Fresh native browser repeat is blocked: CUA inventory reports "The Mac is locked and automatic unlock could not unlock it. Ask the user to unlock the Mac manually before continuing." Chrome is absent; no bypass attempted. A tab-opening timeout preceded this check; no login/UI business mutation was dispatched in the owner browser run. Prior author's desktop/mobile2/2 final receipt is historical evidence; no fresh browser coverage claimed.

Holds748,760,619,622,623,638 preserved. All new QA services are uniquely owned db151release764, with an explicitly empty/asserted synthetic database; existing db151signoutreview and its shared image are preserved. No product-source fix or production records changed. Independent gate is superseding NO-GO.
