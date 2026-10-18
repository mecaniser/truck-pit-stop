# Independent QA and Security receipt — dormant deployment

Reviewer: independent `communications_merge_review` agent; no implementation or direction participation.
Reviewed head: `ed9c363c1cfd5ce40926bec66cb545546844fcb3`.
Integration: `60f6a388`; automation correction: `cde37e9a`; main parent: `46f73e3d`.

GO covers dormant deployment with all three rollout flags false. It does not authorize live SMS enablement.

- 45 focused tests passed on the final head: rollout compatibility, automated producers/guards, assignment, repair-order finalization and maintenance HTTP adapters.
- 80 PostgreSQL tests passed on `cde37e9a`: communications, durable automated outbox and tenant routing. Final application source is identical ignoring whitespace; later changes are tests and whitespace only.
- Dedicated reviewer-owned PostgreSQL database upgraded to `178_merge_maintenance_bindings`, then `181_sms_maintenance_merge`: 165 to173 tables, eight expected SMS tables added, zero removed. Repeated upgrade was a no-op. Reviewer database was dropped afterward. No populated customer-row preservation or real-provider acceptance is claimed by this rehearsal.
- Migration181 is the single graph head, joining SMS180 and maintenance178. Existing migrations remain unchanged; both router/model families register.
- Completion retains maintenance finalization and response plus one gated durable enqueue. Legacy SMS occurs after commit only when automation rollout is disabled.
- Default-off automation preserves existing immediate SMS. Existing tenant bindings prevent global sender fallback when tenant routing is disabled.
- Final diff whitespace check passed and reviewed worktree was clean.

Enabling automation requires recovery readiness and coverage of every producing tenant. Keep automation enabled after adoption; pause recovery for operational rollback. Routing enabled without automation adoption fails closed for legacy staff sends without customer identity. Real handset delivery, public signed-callback acceptance, provider registration and channel activation remain separate gates. Protected checks on the final main integration remain mandatory.

No provider calls, production changes, server changes, secret disclosure or shared-database changes occurred during this independent review.
