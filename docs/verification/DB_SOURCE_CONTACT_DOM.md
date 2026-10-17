# DB-SOURCE-CONTACT-DOM verification

Owner: Backend & Integrations. High-risk source evidence lane. Status: implementation; not released or accepted.

## Acceptance criteria

Read the actual unchecked ETS archive control without treating absent, ambiguous or checked controls as complete. Keep exact account navigation, six-column schema, empty search, full single-page footer and pagination proof. Preserve manual profile data and all financial behavior. Require independent QA/security, exact protected CI and a fresh complete source snapshot delivered to ELIS before Done.

## Authenticated source evidence (2026-10-16, approximately 16:54–17:01 UTC)

Read-only CUA locator inspection of an authenticated account contacts page established:
- One search selector; visible empty search and unchecked native checkbox.
- Exactly one text label `Show archived`, no `for`, no nested input.
- Its immediate wrapper contains one `.inputContent > label.switch > input[type=checkbox]`. The switch label is empty; the text label is its sibling. No checkbox ID.
- Raw heading labels are `customer` and `Contact`; exact six raw columns are `Role`, `First Name`, `Last Name`, `Phone`, `Email`, `notes`. CSS displays uppercase.
- Footer is ` Showing 1 to 2 of 2 results `; no Next button/link on this complete single page.
- General page/locator evaluate is unavailable due pre-dispatch CDP deadline; supported locator attribute/count/text APIs supplied structural evidence. No browser workaround or source writes.

Sanitized jsdom fixture recreates only this structure using invented account/phone values. Extraction is serialized unchanged into the normal collector page; current account and completeness validation remain unchanged.

## Verification

- 18 structural tests pass: observed wrapper, checked/missing/duplicate/wrong wrapper controls, duplicate/nonempty/missing search, wrong account, unbound header, changed schema, truncated columns, missing footer, active/disabled next.
- Existing 10 pure contact contract tests pass; changed test ESLint passes.
- Fresh independent QA/security GO on54450b47: reviewer independently reproduced all28 tests and found no changed-code blocker. PR558 remains held for protected CI and coordinated release; runtime acceptance pending.
- Local runtime preflight: intended isolated branch `codex/ets-archive-control` from main6471943f; clean intake. Port5173 belongs to another task;8000 absent and intended config files absent. Preserved unrelated services/config; local UI is blocked/mismatched. Source tests are not local UI acceptance.

## Active production cycle and release boundary

Exactly one normal off-schedule verification cycle started at16:48:24 UTC on reviewed647 source. Seven runtime source hashes matched the reviewed archive. Daily effective cron remains0UTC. By17:00:17 UTC,105 account-bound snapshots were all incomplete `filtered`; no complete contact acceptance. Existing guards suppress these contacts and hold uncertain matching. Do not modify or restart the active cycle.

Merge/deploy of this correction waits for the coordinated C1 release handoff. No schedule/settings, Google resends, financial writes or manual overrides are included. After protected release, new collection must establish actual complete account evidence and downstream signed receipts; test success is insufficient. Roll back source image on unexpected collector behavior, preserving evidence/holds and avoiding replay.
