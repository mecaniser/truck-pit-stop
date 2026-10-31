Title: Standardize dropdown styling across the platform

Native OS menus made equipment and other selectors look different from the platform. Replace all 57 native dropdowns across 31 feature files with the shared styled menu while preserving their options, values, validation and existing requests.

The controlled PlatformSelect adapter retains native form serialization, required validation, change-event targets and focus refs. The staff role form uses Controller for synchronized resets. Shared menus now preserve disabled choices/fieldsets, restore focus without stealing subsequent typing, dismiss correctly with Escape, adapt to their surface, contain long labels and remain above modals within viewport bounds.

Validation:
- Full frontend suite 2,188/2,188 PASS; 12 dedicated shared-control tests included.
- Production build, changed-source lint and diff integrity PASS.
- Six real-browser desktop/mobile theme cases PASS using disposable test records and shared-control fixtures; screenshots/evidence in output/dropdowns/.
- Independent source and functional review GO; no backend/auth/billing/export contracts changed.

Evidence: docs/verification/DB148_PLATFORM_DROPDOWNS_2026-10-30.md.

Publication approved by the user. Merge and deployment remain separate; no production data changed.
