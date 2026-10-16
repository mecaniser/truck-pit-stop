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

All six protected checks on the final PR head and current main, merge/deployment
evidence, and parent-owned signed-in desktop/mobile acceptance remain required.
The companion cadence documentation records already accepted production work;
this PR does not change its schedule or worker runtime.
