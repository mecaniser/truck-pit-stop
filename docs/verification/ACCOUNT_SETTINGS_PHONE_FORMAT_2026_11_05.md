# Customer profile phone formatting follow-up

Owner: Frontend & UX, Fast UI. Follow-up to PR798/802.

Problem: the saved phone input used the raw server value on load and Cancel, while typing already used formatUSPhone.

Acceptance: loaded/reset values use the existing US formatter; leading1, existing formatting and empty values remain supported; loading/Cancel remains pristine; no API, digit or stored-data change.

Change: use formatUSPhone for both profile forms' initial defaults, the current form's Cancel reset, and the successful-save reset.

Validation: focused profile behavior/summary tests25/25 pass, including five phone cases for raw10 digits, leading1, already formatted, empty and Cancel. No save request is made by load/Cancel. Actual sample preview visually displays the existing standard format on load; Save changes stays disabled. Phone-field values are redacted by the browser DOM adapter, so numeric/format comparisons through that adapter are not treated as evidence. Visual browser verification and component assertions establish the result. Desktop and390px layout checked with no overflow.

Runtime: 2026-11-05; intended branch codex/customer-profile-phone-format, base86fe9cc751367ace1931d43136819fa6f27c0895, dirty phone changes. Prior task-owned preview PID56781 was rechecked and stopped gracefully. Replacement Vite source /private/tmp/customer-profile-phone-format/frontend, listener83405, http://127.0.0.1:5187/account-settings-preview.html?tab=profile. Synthetic in-memory API adapter; no backend/database/provider connection. Other-task ports5173/8000 preserved. Design preview aligned and browser-verified; full-stack check reserved for the authorized production follow-up. Three preview fixture files remain untracked and are not part of the release.

Protected CI, production deployment and signed-in acceptance pending.
