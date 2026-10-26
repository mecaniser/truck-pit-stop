# DB-036 trip departure format parity

Backend & Integrations owns codex/motive-trip-date-parity from6ca27c5d. Parent approved this narrow contract before implementation; independent diagnostic_gate required. No production authority.

The existing rendered trip normalizer explicitly supports numeric `%m/%d/%Y %I:%M %p` and named-month `%b %d, %Y, %I:%M %p` timestamps. New populated-proof parsers supported only numeric timestamps. A synthetic existing-contract named-month row reproduces rejection. Runtime canary reported87 authoritative/response/DOM identities but dom_identity_invalid; the live format cause is not yet proven.

Acceptance: JS and Python proof identities accept exactly these two existing grammars and produce identical canonical provider/New York minute identities and digests. Preserve strict calendar/time validity, DST ambiguity/nonexistence rejection, provider link validation and duplicate/bijection enforcement. Include ongoing/missing-location source rows in completeness without changing importer exclusions or authorizing their import. Add only fixed bounded counts for numeric/named/unknown timestamp shapes, invalid links/identities and duplicate canonical identities; no raw rows or values. Test valid mixed forms, malformed dates, clock/calendar edges, DST folds/gaps, duplicate cross-format identities and unchanged proof/page negatives. Runtime strict canary remains required before imports.

Local runtime preflight: no5173/8000 listeners; controller dry-run blocked missing backend/.env and Vite. No secrets copied; no local browser readiness claim.

Verification: owner80 focused Node and59 Python tests passed. Independent source/security gate passed81 Node (including DOM) and52 focused Python checks, reviewing the final mixed-format collector integration and malformed-cell diagnostic guard. Diff check passed. Runtime canary remains pending; the named-month live cause is still a hypothesis until exact response/DOM parity succeeds.
