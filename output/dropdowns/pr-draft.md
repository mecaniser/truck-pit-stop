Title: Standardize dropdown styling across the platform

Native OS menus made equipment and other selectors look different from the platform. Replace all57 native dropdowns across31 feature files with the shared styled menu while preserving their options, values, validation and existing requests.

The controlled PlatformSelect adapter retains native form serialization, required validation, change-event targets and focus refs. The staff role form uses Controller for synchronized resets. Shared menus now preserve disabled choices/fieldsets, restore focus without stealing subsequent typing, dismiss correctly with Escape, adapt to their surface, contain long labels and remain above modals within viewport bounds.

Validation:
- Full frontend suite2188/2188PASS;12 dedicated shared-control tests included.
- Production build, changed-source lint and diff integrityPASS.
- Six real-browser desktop/mobile theme casesPASS using disposable test records and shared-control fixtures; screenshots/evidence in output/dropdowns/.
- Independent source and functional reviewGO; no backend/auth/billing/export contracts changed.

Evidence: docs/verification/DB148_PLATFORM_DROPDOWNS_2026-10-30.md.

Local draft only. No push, PR publication, merge, deployment or production-data change.
