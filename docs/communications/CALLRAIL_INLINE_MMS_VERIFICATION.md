# DB-COMMS-017: inline incoming MMS verification

Owner: Backend & Integrations. Contract: [authenticated image viewing](CALLRAIL_INLINE_MMS_CONTRACT.md). Branch: `codex/callrail-inline-mms`. Production release remains separate from local implementation evidence.

## Scope

Incoming CallRail image candidates load through staff-authenticated, tenant-scoped manifest and image endpoints. The browser receives re-encoded JPEG/PNG blobs, without provider URLs or credentials. Staff can expand a preview and close with Escape; captions, received times, drafts and automatic reply routing remain intact. Receipt intake, outbound messaging, forwarding, consent and all three SMS rollout flags are unchanged. No migration, image backfill or permanent media storage.

CallRail retains the source image. If its media has expired, is unsupported, or requires a redirect outside the strict API contract, the inbox displays a concise unavailable state with manual Retry. Actual provider redirects have not been verified; this implementation fails closed on all redirects. Synthetic provider/image evidence does not establish actual provider image availability.

## Local runtime

New isolated worktree on main `3816c28cc371f0d6f3516130def06079df849ddd`. The dirty root checkout and older local sessions were preserved. API `http://127.0.0.1:8013`, frontend `http://127.0.0.1:5193`, both source roots confirmed using listener PIDs and working directories. Frontend proxy points to that API; direct and proxied readiness passed. A new synthetic-only database `communications_local_inline_mms_20261022` on loopback55460 was migrated to existing schema187; Redis loopback6386/db13. All three rollout flags false; no real provider keys. Dedicated local fixture denies outbound CallRail and Twilio network paths and serves generated synthetic raster bytes through a mocked media transport.

Signed-in IAB acceptance used Alex Demo in the synthetic shop. Verified incoming image thumbnail, caption/time, expanded dialog, Escape/close focus restoration, retained compose draft, unchanged automatic receiving-number reply route, ordinary SMS history, and390×844 compact layout. No send/toggle/assignment/resolution action. Private screenshots and runtime receipt remain outside the repository. Final source restarted on API PID88968; frontend PID79440 retained. Both listener working directories match this worktree. Direct and frontend-proxied `/health/ready` report database/Redis ready. Final-source desktop1366×900 and compact390×844 inline/expanded-image acceptance passed; Escape restores thumbnail focus. Synthetic draft was cleared after preservation checks. Local preview is aligned and browser-verified at http://127.0.0.1:5193/dashboard/messages.

## Gate findings and corrections

Independent review returned the first backend candidate for debug HTTP core response-header logging, actual app5xx error-envelope mismatch, malformed Content-Length and deeply nested JSON exceptions. Owner corrections suppress only private-request traces while retaining unrelated concurrent logs, return only known sanitized media errors through the actual app stack, and bound/reject hostile parsing. Parent corrected the synthetic harness to explicitly deny CallRail dispatch; no send was attempted. Actual ASGI tests also identified global middleware overwriting no-referrer, requiring an attachment-specific privacy policy. Phone JPEG orientation is applied before fresh-pixel output strips metadata.

Owner and fresh independent focused suites, final runtime receipt, protected CI and PR state will be appended below. No production image or verification-code contents were retrieved. The former one-receipt release monitor stays paused; this feature does not resume it.

## Final independent gates

Owner and fresh independent backend:98 passed (76 media cases plus22 existing receipt regressions). Frontend:56 passed, changed-source ESLint and TypeScript passed. Independent additional15 adversarial cases passed, including actual ASGI staff/tenant denial before credential access and private headers on401/422. Fresh independent QA/Security GO after all returned findings; synthetic-only, no provider/production calls. Decode work can finish bounded raster processing after an awaiting request is cancelled; it performs no provider I/O or persistent write.

Latest main remains3816c28 at source freeze. Protected PR CI, merge, deployment and actual-provider runtime acceptance remain pending; this item is not Done.

## Protected CI external blocker

PR627 head`e97bebb18700f1deed1bafb49cc2230115a61df7`, run39830751878: migration, backend critical/full, frontend critical/full and dependency preparation passed. Playwright smoke failed during service initialization before checkout/tests because pinned public ECR Postgres pulls returned `toomanyrequests: Data limit exceeded`. One targeted setup-job retry reproduced the same external limit; original failure retained. No test/assertion/timeout changes or further retries. Required gate remains failed; PR unmerged and feature undeployed. This local closeout note awaits eventual release-record commit; no app source edits after reviewed head.

## Current-main integration prepared

Local merge80556e05 incorporates main4ddf8d86 and preserves both board histories. MMS application/test/fixture content is byte-identical to independently reviewed e97bebb1; no CI policy/test/deadline change. Later PR623 smoke job120015667506 successfully downloaded the same pinned ECR Postgres image at18:41UTC and passed5 tests, providing evidence that the prior registry limit has recovered. Publication and one new-head automatic CI set wait for the coordinator to release the serial619/622 hold. No production changes.

## Repeated ECR setup failure and source correction

Current-main headc734188d/run39837492814 reproduced ECR `Data limit exceeded` before checkout/tests, despite623 intervening success. No old-head retry. Canonical Docker Hub raw manifests independently retrieved with `docker buildx imagetools inspect --raw`; SHA256 hashes exactly equal existing Postgres c961aa287d8698297cb26cdfadfbe9fd2cbaf77e53cfffe9636e8d8a1e4d842c and Redis858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499 pins. Proposed correction changes only image registry host to docker.io/library; immutable images and all service/test/runner/deadline settings remain identical. Fresh independent gate and protected corrected-head CI required.

Fresh independent QA/Security GO: exact workflow byte comparison proves only the two registry hosts change; independently fetched manifests match both immutable pins and contain Linux amd64 entries. actionlint and diff checks pass. Reviewed MMS app/test/fixture diff against prior GO remains empty. Run39837492814 completed with all application gates passed and smoke setup failure retained; publish one corrected candidate, no duplicate dispatch.

## Merge and queued deployment

PR627 merged1bf3b8de815679be00a3f834b222f331236fb6a2 after all six strict protected checks and preparation pass on880a622c46a752822b2bb0350c854cb0bd1c9b44/run39838291168. Checked and merged trees match1eaa5afba36cd28b8b0c545b49ea9fb1225fa2c5. Automatic Railway Web39620406-18cb-4d45-8736-6f0fa29bd1e6 and Worker754c9536-5c2f-438d-b7a6-72158fc4cfbb queued for that exact source; no manual deployment/retry. Prior production4ddf8d86 API/website SHA healthy, DB/Redis ready, all3SMSflagsunset/defaultfalse bothservices. Private readonlybaseline saved, no datawrite/providerfetch/send. Only stored MMS is excluded verification-code image; requested ordinary truck photo. Successful deployments, servedSHA and authenticated actualimage acceptance remain pending. This release note is local for eventual protected closeout; not Done.

## Successful exact-source deployment

Web39620406-18cb-4d45-8736-6f0fa29bd1e6 and Worker754c9536-5c2f-438d-b7a6-72158fc4cfbb both SUCCESS on1bf3b8de815679be00a3f834b222f331236fb6a2. API and website `/build-version` report that fullSHA and build19:28:14.119UTC. DB/Redis readiness passes. All three SMS rollout flags remain unset/defaultfalse on both services. Unauthenticated media endpoint denied401 with private/no-store/max-age0 and no-referrer. Postdeploy readonly full-row digest comparison unchanged across SMS, threads, customers, CallRail mappings/bindings, reply routes and sendoperations; schema187 retained. Existing automatic deployments used, no manual retry or datawrite/providerfetch/send/configuration change.

Signed-in live inbox refreshed on a plaintext inquiry with empty draft, avoiding excluded verification-code image. User told to wait until deployment confirmed before sending ordinary truck photo. Actual provider image preview/expanded viewer and reply-route acceptance still pending; do not mark Done or pause monitor until verified.
