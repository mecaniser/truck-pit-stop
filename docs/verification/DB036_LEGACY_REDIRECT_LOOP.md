# DB-036 provider legacy redirect loop

Owner: Backend & Integrations. Branch: codex/motive-legacy-roundtrip, base e9c1b232. Scope: prepare fix PR only; no merge/deploy/manual worker/schedule/credential changes.

## Actual cause and evidence boundary

Fresh headless Chromium used the collectors' public navigation/context settings with no credentials. A failing lookup attempt reached a fully loaded document, loaded fallback JavaScript and had no page errors. The real advertised link executed this HTTP chain:

1. https://auth.gomotive.com/login/legacy_fallback — 302
2. https://account.gomotive.com/log-in — 303
3. https://auth.gomotive.com/login — 303
4. https://auth.gomotive.com/login/lookup — 200

The final page retained its lookup input and lacked legacy credentials fields. A successful comparison followed the same chain but step3 returned200 and displayed legacy fields. The precise failure was login_form_timeout, matching recurring worker diagnostics. It was not a lost click or proven hydration issue. The provider's publicly served ciam_fallback_login script synchronously invokes its fallback endpoint through the observed link; no cookie values or OAuth queries were inspected or recorded.

The first bounded fresh-context investigation reproduced one failure among10 app navigations; direct public lookup also succeeded. A further maximum20 probe stopped at attempt15 after capturing the complete failing chain (attempt6 captured success). A separate bounded second-click investigation stopped at attempt6 after a proven first-roundtrip failure recovered on the second provider-link click within15seconds. Attempt4 in that investigation remained in lookup after both clicks. Therefore the correction improves bounded recovery; it cannot guarantee the provider will choose legacy login.

## Correction

Keep the existing15second total preflight deadline. Permit at most two actual provider-link clicks, never direct fallback navigation or lookup submission. A second click requires a main-frame navigation followed by DOMContentLoaded of a new returned lookup document; hash-only changes and pending navigation do not qualify. Revalidate exact trusted auth origin/path and unique visible link/href before each click. Credential fields and submit button still require the final trusted /login form; intermediate account.gomotive.com receives no credentials. A second completed return to lookup raises static login_legacy_redirect_loop. Distinct retry/redirect phases remain allowlisted; raw errors and URLs are not logged. Listeners are removed on all exits.

## Verification

Local runtime preflight blocked: no approved backend/.env or Vite in isolated worktree, no5173/8000 listeners. No services/databases changed. Tests use isolated Chromium fixtures. Real redirect-chain tests use a local TLS server plus fail-closed host resolution mapping provider test names to127.0.0.1 and all other names to~NOTFOUND. Existing intercepted fixtures likewise block external DNS. This corrects an initial test-harness issue: Playwright route interception did not intercept every redirected request; four initial fixture results were invalid and were not accepted as application proof. No credentials were used in those tests.

Browser fixtures cover the real multi-origin HTTP chain returning to lookup then recovering, permanent loop cap2, pending slow navigation with no second click, unsafe link on the returned document, foreign final origin, and same-document hash changes. Existing direct legacy, link validation, credential guards and diagnostic privacy cases remain. Owner focused results and independent gate recorded below when complete.

Natural scheduled production acceptance is outside this PR preparation. No live credential authentication, collection/import success or deployed recovery is claimed.

Owner final focused run:68/68 pass, including26 Chromium fixtures and7 diagnostic cases; diffcheck clean. Independent QA/Security GO:33/33 tests (26 Chromium plus7 diagnostic privacy), clean diffcheck; no reviewer edits. Protected PR CI remains pending.
