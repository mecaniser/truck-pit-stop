# DB-COMMS-027 — Linked contact display

Owner: Frontend & UX. Existing display contract correction with CRM visibility review.

## Contract and acceptance

The existing customer_name/company response fields use the explicitly linked
contact name and customer company when that association is valid and visible to
the existing customer-context roles. Tenant, soft deletion, contact/customer
membership and transport-customer consistency checks match the sidebar. Invalid
or unavailable links retain the prior safe display. A blank linked person name
falls back to company. Unlinked inquiries remain New inquiry.

No IDs, conversation kind, reply route, send policy, consent, draft key or flags
change. CRM links are not delivery identities. After a successful link, refresh
the selected conversation through the existing guarded detail/read path. Both
list and header prefer company over the inquiry phone fallback.

## Evidence

16 PostgreSQL context tests pass; 52 frontend adapter/context/inbox/component tests
pass, including live rerender of a linked name/company with the draft retained.
TypeScript, changed-source ESLint and diff checks pass. Independent reviewer
linked_display_review: code/security GO, seven additional guard scenarios pass.
First new PostgreSQL test failed because its fixture violated inquiry identity
constraints; corrected to use the existing valid inquiry fixture, no guard bypass.

October 29 local runtime: codex/linked-contact-display at 9bcf8ab plus scoped
edits. API8013 and Vite5193 serve the callrail-inline-mms worktree; dedicated
communications_local_023_20261028 database on loopback55460 and Redis6386/db14
preserved. All three SMS flags forced false and external provider sends denied.
Proxy readiness passed. Signed-in synthetic Taylor Context / Context Fleet A
renders in list and header, desktop and 390x844. Existing synthetic draft and
reply route remain unchanged. Screenshots /tmp/comms027-desktop.png and
/tmp/comms027-mobile.png. Preview http://127.0.0.1:5193/dashboard/messages is
aligned and browser-verified for these edits. No production association changes.

Protected CI, merge and deployment remain pending. Not Done.
