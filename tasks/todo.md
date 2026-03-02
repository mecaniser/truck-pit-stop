# Driver Recruiting Agent SOP - Task Plan

## Plan
- [x] Draft ATS-ready SOP scope, objectives, and role responsibilities.
- [x] Define end-to-end pipeline stages with explicit entry/exit criteria and SLAs.
- [x] Create copy-ready candidate message scripts (SMS + fallback email) by stage.
- [x] Define standardized screening questionnaire with answer options and capture fields.
- [x] Implement deterministic pass/fail logic with weighted scoring and disposition rules.
- [x] Map logic to ATS statuses, tags, tasks, and automation triggers.
- [x] Add operational guardrails, QA checks, and KPI dashboard definitions.
- [x] Review for clarity and plug-and-play usability.

## Progress Notes
- Initialized planning artifact for this deliverable.
- Added ATS-ready SOP at `docs/DRIVER_RECRUITING_AGENT_SOP.md`.
- Added import templates:
  - `docs/templates/driver_message_scripts.csv`
  - `docs/templates/driver_screening_questions.csv`
  - `docs/templates/driver_decision_rules.json`
- Verified template formatting and schema consistency against SOP sections.

## Review
- Deliverable is implementation-ready for most ATS automation builders.
- Remaining adaptation required: map exact field names/status IDs to your specific ATS vendor.

---

# SEO Improvements - Task Plan (2026-03-02)

## Plan
- [x] Audit existing SEO assets (sitemap, robots, metadata, canonical tags).
- [x] Improve public page metadata with consistent tags for title, description, canonical, robots, Open Graph, and Twitter.
- [x] Add structured data for crawlable public pages.
- [x] Ensure `/sitemap.xml` is served from production backend static routes.
- [x] Align sitemap contents with canonical, indexable public pages and include `lastmod`.
- [x] Verify changes with targeted checks and frontend build.
- [x] Add review notes and residual risks.

## Progress Notes
- [x] Initialized SEO implementation plan using the `seo` skill workflow.
- [x] Added reusable page-level SEO utility: `frontend/src/lib/seo.ts`.
- [x] Upgraded public page tags and JSON-LD on landing and enrollment pages.
- [x] Added `noindex, nofollow` metadata for login.
- [x] Updated root static SEO tags in `frontend/index.html`.
- [x] Updated crawl directives in `frontend/public/robots.txt`.
- [x] Updated sitemap URLs and `lastmod` in `frontend/public/sitemap.xml`.
- [x] Added backend static route serving for `/sitemap.xml` in `backend/app/main.py`.
- [x] Verified frontend build succeeds with `npm run build`.

## Review
- SEO foundation is now in place for indexable marketing pages (`/` and `/enroll`).
- Login and private application surfaces are explicitly de-prioritized for indexing.
- Residual risk: static sitemap `lastmod` values require manual updates when content changes.
