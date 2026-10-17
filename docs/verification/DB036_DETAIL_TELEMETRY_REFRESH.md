# DB-036: refresh telemetry in an open truck detail

Owner: Frontend & UX. Fast UI lane. Branch `codex/truck-detail-live-telemetry`.

## Acceptance and change

The Fleet Board polls every 60 seconds, but the selected truck detail used its
initial detail response indefinitely. Refresh that existing authenticated query
at the same 60-second interval so new speed observations appear without leaving
the detail. Keep its truck-specific cache key and endpoint, and preserve the
existing five-minute current-speed cutoff, explicit zero and independent source
timestamps. Do not add polling to incident, inspection, history or parts queries.
No API, data, worker, permission or layout change.

## Local evidence

- The new actual-QueryClient regression failed against the original component:
  the detail still displayed 45 mph when the next response contained 0 mph.
- After adding `refetchInterval: 60000`, the open detail receives the new zero,
  keeps it visible through its five-minute source-age boundary, and expires it
  when repeated responses still contain that same old observation. Incident
  and inspection queries each run once.
- `TruckDetailHarden.test.tsx` and `TruckTelemetry.test.tsx`: 16 tests passed.
- Changed-source ESLint, TypeScript and production Vite build passed.
- `git diff --check` passed. Rebase from `d5cb6628` to `7299722d` preserved both
  implementation and test files byte-for-byte; no broad local rerun was needed.

## Runtime boundary

Local preflight on 2026-10-16 at 13:52 UTC: this clean managed worktree started
from `d5cb6628`; parent-owned frontend5173/PID27324 serves the separate
`motive-driver-records` checkout and was preserved. Backend8000 has no listener,
and no approved backend configuration exists in this checkout. The configured
development proxy defaults to `http://127.0.0.1:8000`; no service was started,
secrets copied, provider configuration changed or browser controlled here.
This checkout is not locally served. Full-stack local/browser acceptance is
blocked; component tests are not claimed as signed-in browser acceptance.

## Release

PR554 passed all six protected checks in run38918827921 on exact head
`e8e6c059e91e3d27ccac7904238275f6745fb1c6`. It merged at 15:37:20 UTC on
2026-10-16 as `4061aaa83935fb67723ac5fcd340957781aae850`; tested and squash
trees both equal `52f42af2c54dd1667dc38329d7a9a8fae642ba50`. Only the redundant
post-merge main run38925435576 was canceled after tree equality was verified;
the six required PR checks passed independently.

Web deployment `5b8a025c-5d3f-421c-9521-d8c386386aef` is SUCCESS. The public
build endpoint serves that exact merge SHA (built 15:40:58.940 UTC), and database
and Redis readiness pass. Signed-in production acceptance at 1280x900 and
390x844 passed:

- Truck860 initially showed explicit 0 mph, source observed around 11:42 AM EDT,
  captured 11:44:23 AM. Its safety score85 remained visible beside the driver.
- Without navigation or reload, that observation expired: at 15:47:37 UTC the
  detail showed Speed unavailable and motion unknown, retaining location/score.
- Still without navigation or reload, the normal detail poll received fresh
  0 mph by 15:49:43 UTC. The source timestamp advanced to around 11:47 AM EDT,
  captured 11:48:54 AM; location age and stopped state updated with it.
- Mobile document client/scroll widths both390; desktop/mobile labels and
  timestamp popover were readable. No new warning/error console entries during
  this acceptance window. Viewport restored and the user tab returned to Fleet map.

Private evidence is under `output/detail-refresh/`: before/expired/after JSON,
release receipt, desktop/mobile screenshots and the bounded console observation.
This is authenticated production evidence, separate from local component tests.
The companion cadence documentation records accepted production work; this PR
changes neither the collector schedule nor worker runtime. The separately
identified daily driver identity timeout recovery remains open in PR555, held
behind the coordinated PR551/550 release sequence; it does not negate this
UI acceptance and is not claimed complete here.
