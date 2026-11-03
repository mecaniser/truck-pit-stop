# PR764 logout ordering correction

Owner: Auth/API & Frontend. Local branch fix/pr764-logout-response-isolation, based on preserved failing-regression commit faa369a7 and PR764 reviewed711c136c. Release hold remains: draft, no merge or deployment before full checks, independent gate and browser acceptance. Command access is available; native browser last explicitly reports Mac locked.

## Contract

WorkOS logout still blacklists the presented local access JWT JTI for its remaining lifetime and deletes only the presented opaque server session. It now emits no Set-Cookie headers. HTTP cookie deletion cannot compare-and-delete an old value, so even an otherwise valid logout response must not expire a newer tab's replacement cookie. Already-revoked HttpOnly cookie copies remain until their existing expiry or next login overwrite; they confer no authority. JSON endpoint response, request shape, token/session lifetimes, permissions and legacy logout remain unchanged. No migration, credential or production setting change. This applies to successful revocation; backend failures are not claimed as successful logout.

Client logout captures its logout epoch in request metadata. The actual Axios request interceptor reconciles durable peer state before dispatch and cancels explicitly stale epochs, rather than stamping them with the new session and sending the old logout under B's cookies. Same-session retries/rotation keep their epoch; replaced-session retries cancel. Metadata remains client-side; no new HTTP header or server parameter.

## Evidence

Original failing actual-ASGI/cookie-jar regression at faa369a7 remains in history and workspace workos-overlap-real-asgi.json/.log: B me200 before A response, then me401/refresh401 while B server session persists. The same desired me200 assertion is preserved and strengthened. Current tests cover A-to-new-A and A-to-B replacements through actual app routes, SQLite/FakeRedis, controlled WorkOS exchange/membership, and standard cookie jar. Both replacement me/refresh200 after A response; old-cookie /workos/me, /auth/me, refresh all401 in a client with no frontend state. WorkOS suite28/28 pass6.31s; fixture network remains disabled. Provider interactions are simulated, not live vendor acceptance. Test artifacts use pytest tmp_path, not a required external directory.

Actual-Axios pre-dispatch tests fail3/pass2 before intent binding and pass5/5 after. Related API cancellation/refresh, auth-store and socket checks54/54 pass. Independent request-intent/metadata-retry assessment60/60 pass, including same-epoch token rotation and reused caller config. Independent revocation-only endpoint probes4/4 pass and contract/source assessment accepts revoked-cookie retention without authority. Original backend full and frontend clean results belong to prior711 head; fresh full checks are required after this correction.

Independent receipts retained in workspace pr764-release-evidence: INDEPENDENT_REVOCATION_ONLY_CONTRACT.md and existing security review/dispatch evidence. Initial focused extension exposed incomplete simulated membership responses; completed provider-boundary fixture without weakening assertions, then28/28 passed.

## Release limits

No fresh native-browser overlap was executed while the Mac is reported locked. Required later: warm peer tabs, hold real logout response through replacement login, same/different shop, Back/reload, no old UI revival, old-session denial and current-session continuity on desktop/mobile. Real WorkOS vendor exchange remains a separate limit unless actually exercised. Old backend instances continue emitting deletion headers until rollout fully replaces them; keep release hold and verify exact deployment. Do not claim all cross-session cookie writers are covered by this narrow logout response correction.

Rollback requires reverting this focused change and redeploying; no data migration/financial rollback. Stop release for stale private display, replacement logout, revoked-cookie access, unexpected request replay, failing required check or material independent finding. No real payment, production financial mutation, formal PR review approval or held-work change.
