# Motive browser trip refresh

Supported runtime: Codex desktop CUA with the authorized, signed-in Motive browser.
This is a browser-assisted collector, not an OAuth integration or a standalone
headless process. The Mac and Codex must be available. Session expiry/MFA requires
the owner to sign in; never store passwords, cookies or session exports.

## Run

1. Use the linked DB-036 worktree. Read the collection contract. Acquire a private
   run directory through `openState` from `motive_collector_state.mjs`; keep its
   exclusive lock until collection/import finishes. An existing lock requires
   checking that the previous process ended, not blindly removing it.
2. Before **and after** capture, open the observed Motive Admin → Company page and
   verify the visible company is the authorized company in the private mapping.
   Record the visible label and check time in the private run manifest. A mismatch,
   inaccessible page, or expired login stops the run, including empty reports.
3. Daily window: previous two local dates through today (America/New_York). Resume
   failed windows first. Consult `output/history-run-manifest.json`; superseded
   captures are not pending windows. Historical backfill uses bounded windows of at most31 days;
   prefer seven days because large rendered tables slow the browser. Daily refresh
   covers trips only; fleet telemetry snapshots use their separate importer.
4. Import `collect_motive_trips.mjs` in CUA. Navigate to `reportUrl(start,end)` and
   check the selected visible range. Record the source total from the report's
   trip detail counter (e.g.1/120), then return to the report. For an explicit empty
   report record zero. Do not infer completion from a pause in scrolling.
5. Start `newWindow(start,end)` or restore a private checkpoint. Call
   `advance(tab.playwright,nativeTab,receipt,r=>state.write('window.json',r))` in
   bounded calls. Each call reads only rendered columns and scrolls. Allow the
   source to finish loading between calls; inspect the new footer before continuing.
   Repeated unchanged content stays partial; review delays/errors before resuming.
   If a browser call fails, preserve the checkpoint and recover the same tab.
6. `finalizeWindow(receipt,total,countEvidence)` must succeed before normalization.
   Any conflicting provider/departure identity, missing tail or wrong filters keeps
   the window partial. Company verification is a mandatory caller precondition;
   the module does not claim to check a company label absent from the Trips page.
   If an ongoing trip changes while scrolling, preserve the conflicting checkpoint.
   When the entire current report is visibly rendered and its source total matches,
   a new window may capture that complete current DOM once and finalize independently.
   Never remove versions merely to force a count match or treat a partial DOM as complete.
7. Assemble exactly `{tenant_id,company_label,windows}` with each window's
   `start,end,source_read_at,status,rows`. Keep completion/account evidence in the
   separate private manifest. Prepare using:

   ```sh
   python3 backend/scripts/prepare_motive_trip_history.py --input CAPTURE.json \
     --mapping MAPPING.json --prior PRIOR.json --output-dir NEW_PRIVATE_DIRECTORY
   ```

   Mapping entries bind provider ID to verified VIN and current membership start.
   Never match by unit alone. Refresh membership before import. Include previous
   normalized imported rows as PRIOR so existing frozen metrics remain unchanged.
   Quarantine unknown vehicles, ongoing/ambiguous trips and source conflicts.
8. Use `scripts/run_motive_trip_batches.py --help`. Supply private normalized input,
   exact current deployment SHA, authorized tenant/actor and Railway service IDs.
   Run dry-run first, inspect counts/exclusions, then the same command with `--apply`
   and a new receipt path. It preserves unrelated vehicle/telemetry/repair tables,
   batches in one transaction and verifies an unchanged replay before commit.
   A transport failure means the outcome is unknown: retry the exact payload.
9. Save committed rows as the next PRIOR only after confirmed receipts. Record
   created/unchanged/excluded counts and available imported dates. Verify Trips in
   DieselBridge when its session is available. Close the lock in `finally`.

No captured data or receipts belong in Git. Directory0700/files0600. Do not label
source-read time as trip observation time. Missing imported dates are not proof of
zero activity. No universal one-year Motive retention policy has been established.
