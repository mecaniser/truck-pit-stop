# Customer profile phone formatting follow-up

Owner: Frontend & UX, Fast UI. Follow-up to PR798/802.

Problem: the saved phone input used the raw server value on load and Cancel, while typing already used formatUSPhone.

Acceptance: loaded/reset values use the existing US formatter; leading1, existing formatting and empty values remain supported; loading/Cancel remains pristine; no API, digit or stored-data change.

Change: use formatUSPhone for both profile forms' initial defaults, the current form's Cancel reset, and the successful-save reset.

Validation: focused profile behavior/summary tests25/25 pass, including five phone cases for raw10 digits, leading1, already formatted, empty and Cancel. No save request is made by load/Cancel. Actual sample preview visually displays the existing standard format on load; Save changes stays disabled. Phone-field values are redacted by the browser DOM adapter, so numeric/format comparisons through that adapter are not treated as evidence. Visual browser verification and component assertions establish the result. Desktop and390px layout checked with no overflow.

Runtime: 2026-11-05; intended branch codex/customer-profile-phone-format, base86fe9cc751367ace1931d43136819fa6f27c0895, dirty phone changes. Prior task-owned preview PID56781 was rechecked and stopped gracefully. Replacement Vite source /private/tmp/customer-profile-phone-format/frontend, listener83405, http://127.0.0.1:5187/account-settings-preview.html?tab=profile. Synthetic in-memory API adapter; no backend/database/provider connection. Other-task ports5173/8000 preserved. Design preview aligned and browser-verified; full-stack check reserved for the authorized production follow-up. Three preview fixture files remain untracked and are not part of the release.

Protected CI, production deployment and signed-in acceptance pending.

## Released and verified

PR803 passed all seven protected checks on18604dd1c1d0869893ff1521656ed2c64ab210ce, Quality gates run42107319448. Backend jobs were scoped as unaffected, not fresh backend-suite coverage. Protected squash mergeea41a9fd5e84642a68a2c948f0ca7dccd1f161b9 completed2026-11-05 at20:59:06UTC. Checked and merged frontend trees are identical.

Automatic production deploymentf613d736-25eb-45f6-94d3-805bbbd90f1c succeeded on that exact merge SHA; the served build stamp matches. Production readiness reports database/Redis OK. No forced deployment, configuration, provider or worker action. Rollback reference: deploymentb2392fc6-2327-44a1-b014-7f8e4d22949a, source86fe9cc751367ace1931d43136819fa6f27c0895.

Actual signed-in customer acceptance used a separate production settings tab because the user's original tab had moved to an invoice. The loaded phone display was visually confirmed formatted. Save changes is disabled and there is no unsaved indicator immediately after loading. A temporary first-name edit followed by Cancel restored the clean form through the same reset path. At390px, Phone is visible and there is no document overflow. The viewport override was cleared and the clean Profile page left available.

Phone values remain redacted by the browser DOM adapter, so adapter-derived string comparisons are not used as numeric/display evidence. Actual visual inspection and the focused component assertions establish formatting. No private contact values are copied into this record.

No customer Save, phone update, credential, card, invoice or payment mutation was submitted. This is a display/default-value fix; no stored-data correction or migration.

The phone-formatting follow-up is Done.
