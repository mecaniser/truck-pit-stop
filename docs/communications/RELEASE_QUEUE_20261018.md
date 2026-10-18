# Authorized merge queue — 2026-10-18

Owner: Release & Reliability. Scope: PR534, PR536, PR560, in that order.
Twilio submissions and real-SMS/channel enablement remain held.

## PR534 — release documentation

- Checked head `a21d376e6fc5bd7edf1c232bc8bac384e723a1c9`; all six protected checks passed in run39158483435.
- Squash merge `363cedb11fa960765ca47fada44986117fc1b681` at19:57:54 UTC.
- Railway production Web `2bdc6bec-e303-40d6-81e5-5e7a58847f69` SUCCESS at that SHA. Public `/build-version` matches; `/health/ready` database/Redis ready. Messages route HTTP200 and authenticated browser reload passed after deployment.
- Main push run39161128260 canceled as duplicate after exact Git-tree identity `4a3d65e27869325fdcd946dc3d315915cdce96e9` matched the fully checked PR head. This cancellation is not a passed test and did not alter branch protection.
- Documentation only; no Worker source change or Twilio operation.

## PR536 — compact toast UI

Refreshed onto the PR534 merge as `824eed6d816bdae6e51408d0639548f38f591b80`; fresh protected run39161150482 pending. Merge/deploy not yet claimed.

## PR560 — communications foundation

Conflict resolution integrates released maintenance behavior, single graph head181, and a default-off automation rollout compatibility switch. Independent dormant-deployment GO and isolated migration/fixture evidence are in `MERGE_INTEGRATION_REVIEW_20261018.md`. Fresh final-main CI, merge and Web/Worker deployment remain pending. Existing SMS behavior is preserved while automation rollout is false; real SMS/provider registration and activation remain separately held.
