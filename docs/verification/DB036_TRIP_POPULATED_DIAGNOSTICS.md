# DB-036 populated proof runtime diagnostics

Backend & Integrations owns this high-risk diagnostic-only follow-up on branch codex/motive-trip-proof-failure, base974245ae. Independent diagnostic_gate approval is required. No production actions are authorized here.

The first strict proof canary failed at populated_capture before import. Its catch discarded the cause, so the actual UI/schema/proof failure remains unknown. Documented response identity fields remain hypotheses until runtime parity succeeds.

Acceptance before implementation: preserve every capture, proof, import and retry decision. Report only static allowlisted UI/proof phases and first failure codes; fixed bounded finite aggregate counts and fixed field-presence/type enums. Snapshot sanitized diagnostics before cleanup and sanitize again at the canary output sink. Never include raw exceptions, payloads, rows, identities, URLs, headers, arbitrary keys or field values. Cover the actual canary path with synthetic positive/negative fixtures and malicious strings. Distinguish no matching request, incomplete tail, malformed schema, invalid identities/time, duplicate/conflicting observations, DOM mismatch and UI failures in one approved evidence run. No diagnostic result grants import permission.

Runtime preflight: no local5173/8000 listeners; controller dry-run blocked by missing backend/.env and frontend Vite. No secrets copied or local rendering claimed. Existing proof regression suite and independent security review are required before PR/release.

Verification: owner 67 focused Node tests and one DOM test passed, including actual canary success/failure paths and deployed adapter layout. Independent diagnostic_gate reviewed source/security and independently passed 60 tests before seven additional diagnostic-only regression tests were added. Source acceptance predicates are unchanged. Diff check passed. Runtime cause remains unknown; next canary is release-owner controlled, with imports prohibited.
