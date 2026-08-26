#!/usr/bin/env python3
"""Unattended nightly ETS -> DieselBridge sync, with sanity guardrails.

Every prod write this session went scrape -> dry-run -> manual comparison
against ETS's own numbers -> commit, and that manual check is what actually
caught three separate data bugs (legacy invoice-number collisions, a
cancelled-invoice coverage gap, labor rows getting multiplied). Running this
unattended removes that human checkpoint, so its place is taken by explicit
gates instead: every step that writes runs its own --dry-run first, the
resulting stats are checked against a ceiling, and only a clean pass proceeds
to --commit. Any failure aborts the run and emails an alert; nothing here
writes speculatively.

The two failure modes actually seen this session are exactly what the gates
target: a scrape that silently under-collects (session timeout, pagination
truncation, ETS changing its page structure) rather than erroring loudly, and
an importer stat blowing past normal daily volume (which is what a stuck
"already covered" guard or a re-triggered duplication bug would look like).

Intended to run as a scheduled Railway service (see railway.ets-sync.json),
not interactively:

    DATABASE_URL=<prod dsn> TENANT_ID=<prod tenant> \\
    RESEND_API_KEY=... RESEND_FROM_EMAIL=... SYNC_ALERT_EMAIL=... \\
    python3 nightly_sync.py
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

SYNC_DIR = Path(__file__).parent
DATA_DIR = SYNC_DIR / "data"
SCRIPTS_DIR = SYNC_DIR.parent
STATE_DIR = SYNC_DIR / "state"

STAGES = [
    "01_scrape_customer_ids.js",
    "01b_scrape_all_vehicles.js",
    "02_scrape_customer_details.js",
    "04_scrape_parts_inventory.js",
    "05_scrape_invoices.js",
]

# Fractional drop vs. the previous successful run's record count that's still
# considered plausible. 15% is generous headroom above normal day-to-day
# churn (retired customers, closed ROs don't shrink these files) while still
# catching a scrape that broke partway through and only got half the data.
RECORD_DROP_TOLERANCE = 0.15
KEY_FILES = ["customer_ids.json", "all_vehicles.json", "customer_details.json",
             "parts_inventory.json", "invoices.json"]

MAX_FAILURE_RATE = 0.02  # a stage's own *_failures.json vs. records attempted

# Derived from 21 days of prod history: invoices/day maxed at 15 (avg ~7), so
# 60 is 4x the observed ceiling. Customer/vehicle inserts are bursty (manual
# resyncs have hit 37 in a day) so those get more headroom. These gate the
# *dry-run* stats — a breach skips the commit entirely, it doesn't undo one.
IMPORT_CEILINGS = {"inv_ins": 60, "ro_ins": 150, "cust_ins": 150, "veh_ins": 150}
LEGACY_FIX_CEILING = 25       # renamed + squatters_evicted + payments_renamed
BACKFILL_CEILING = 200        # "updated" on either backfill script

# Arbitrary fixed key for a Postgres advisory lock (any 64-bit int works, it
# just has to be consistent across runs). A live test proved Railway's "skip
# if a previous cron execution is still running" isn't reliable under a tight
# test interval: two overlapping instances both passed fix_legacy_invoice_numbers.py's
# --dry-run gate against the same pre-run state, then one's --commit hit a
# unique-constraint conflict from the other's already-committed rename —
# alerted correctly, but should never have been able to happen. This lock
# makes "only one instance touches the DB at a time" true regardless of
# whether Railway's own overlap detection holds up.
LOCK_KEY = 771198337


def log(msg):
    print(f"[{datetime.now(timezone.utc).isoformat()}] {msg}", flush=True)


def dsn_from_env():
    url = os.environ["DATABASE_URL"].strip()
    return url.replace("postgresql+asyncpg://", "postgresql://").replace("+asyncpg", "")


def acquire_lock():
    """Returns a held connection on success, None if another run holds the lock.

    Deliberately kept open for the caller's lifetime (not closed here) — the
    lock releases automatically when this connection closes, i.e. when the
    process exits, so it can't be left stuck by a crash between acquiring and
    an explicit release.
    """
    conn = psycopg2.connect(dsn_from_env())
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,))
    got = cur.fetchone()[0]
    if not got:
        conn.close()
        return None
    return conn


def send_alert(subject, body):
    api_key = os.environ.get("RESEND_API_KEY")
    to = os.environ.get("SYNC_ALERT_EMAIL")
    if not api_key or not to:
        log(f"ALERT (no RESEND_API_KEY/SYNC_ALERT_EMAIL configured, logging only): {subject}\n{body}")
        return
    try:
        import resend
        resend.api_key = api_key
        resend.Emails.send({
            "from": os.environ.get("RESEND_FROM_EMAIL", "alerts@dieselbridge.app"),
            "to": to,
            "subject": subject,
            "html": "<pre>" + body.replace("<", "&lt;") + "</pre>",
        })
        log(f"alert emailed to {to}: {subject}")
    except Exception as e:
        log(f"ALERT EMAIL FAILED ({e}): {subject}\n{body}")


def abort(subject, body):
    log(f"ABORT: {subject}\n{body}")
    send_alert(subject, body)
    sys.exit(1)


def run_stage(script):
    log(f"scraping: {script}")
    try:
        # 02_scrape_customer_details.js walks every customer's vehicles and
        # service history one Playwright navigation at a time — a full
        # (non-resumed) run against 600+ customers took over an hour in this
        # session's manual runs. A hard timeout here must not raise past this
        # function uncaught, or a slow-but-healthy scrape crashes the whole
        # job with a bare traceback instead of a clean, alerting abort.
        result = subprocess.run(["node", script], cwd=SYNC_DIR, capture_output=True,
                                 text=True, timeout=10800)
    except subprocess.TimeoutExpired as e:
        tail = ((e.stdout or "")[-2000:] + "\n" + (e.stderr or "")[-2000:]).strip()
        log(f"TIMEOUT after {e.timeout}s: {script}\n{tail[-1000:]}")
        return False, f"timed out after {e.timeout}s\n{tail}"
    tail = (result.stdout[-2000:] + "\n" + result.stderr[-2000:]).strip()
    log(tail[-1000:])
    return result.returncode == 0, tail


def record_count(path):
    if not path.exists():
        return None
    try:
        return len(json.loads(path.read_text()))
    except Exception:
        return None


def latest_backup_dir():
    backups = sorted(SYNC_DIR.glob("data_bak_*"))
    return backups[-1] if backups else None


def check_failure_rates():
    for f in sorted(DATA_DIR.glob("*_failures.json")):
        try:
            failures = json.loads(f.read_text())
        except Exception:
            continue
        n_fail = len(failures) if isinstance(failures, (list, dict)) else 0
        if n_fail == 0:
            continue
        base = f.name.replace("_failures.json", ".json")
        attempted = record_count(DATA_DIR / base) or 0
        rate = n_fail / max(attempted + n_fail, 1)
        if rate > MAX_FAILURE_RATE:
            return False, (f"{f.name}: {n_fail} failures ({rate:.1%} of attempted) "
                            f"exceeds the {MAX_FAILURE_RATE:.0%} tolerance")
    return True, None


def check_record_drops(prev_dir):
    if prev_dir is None:
        return True, None  # nothing to compare against yet
    for fname in KEY_FILES:
        prev_count = record_count(prev_dir / fname)
        cur_count = record_count(DATA_DIR / fname)
        if prev_count is None or cur_count is None:
            return False, f"{fname}: missing from this run or the previous one"
        if prev_count == 0:
            continue
        drop = (prev_count - cur_count) / prev_count
        if drop > RECORD_DROP_TOLERANCE:
            return False, (f"{fname}: {cur_count} records vs {prev_count} last run "
                            f"({drop:.1%} drop, tolerance {RECORD_DROP_TOLERANCE:.0%})")
    return True, None


def run_python(script, *args):
    cmd = [sys.executable, str(script), *args]
    log("running: " + " ".join(cmd[1:]))
    try:
        result = subprocess.run(cmd, cwd=SYNC_DIR, capture_output=True, text=True, timeout=3600)
    except subprocess.TimeoutExpired as e:
        log(f"TIMEOUT after {e.timeout}s: {' '.join(cmd[1:])}")
        return False
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        log("FAILED:\n" + result.stderr[-3000:])
    return result.returncode == 0


def gated_commit(label, script, tenant_id, ceiling_check, extra_args=(), needs_yes=False):
    """dry-run -> check stats against ceiling_check -> commit only if clean.

    ceiling_check(stats) returns (ok: bool, reason: str | None).
    Returns True on a clean commit, False (after alerting) on any failure —
    including a ceiling breach, which skips the commit entirely rather than
    writing and then flagging it.

    needs_yes: only import_to_truckpitstop.py has an interactive confirmation
    prompt to bypass for unattended use. Passing --yes to the other three
    scripts fails argparse ("unrecognized arguments") before they even open a
    DB connection — caught correctly by the run_python() check below and
    aborted with nothing written, but worth not tripping in the first place.
    """
    STATE_DIR.mkdir(exist_ok=True)
    dry_stats_path = STATE_DIR / f"{label}_dryrun.json"
    if not run_python(script, "--tenant-id", tenant_id, "--dry-run",
                       "--json-out", str(dry_stats_path), *extra_args):
        abort(f"ETS nightly sync ABORTED — {label} dry-run failed",
              f"{script} exited non-zero on --dry-run. See Railway logs for this run.")
    stats = json.loads(dry_stats_path.read_text()) if dry_stats_path.exists() else {}
    ok, reason = ceiling_check(stats)
    if not ok:
        abort(f"ETS nightly sync ABORTED — {label} tripped a volume guardrail",
              f"{reason}\n\nFull dry-run stats: {json.dumps(stats, indent=2)}\n\n"
              "Nothing was written. This could be a legitimate busy day or a bug "
              "creating/matching rows incorrectly — worth a manual look before "
              "re-running.")
    commit_stats_path = STATE_DIR / f"{label}_committed.json"
    commit_args = ("--tenant-id", tenant_id, "--commit") + (("--yes",) if needs_yes else ())
    if not run_python(script, *commit_args, "--json-out", str(commit_stats_path), *extra_args):
        abort(f"ETS nightly sync ABORTED — {label} commit failed",
              f"{script} passed its dry-run gate but failed on --commit. "
              "Check for a partially-applied state. See Railway logs for this run.")
    log(f"{label}: committed cleanly — {stats}")
    return True


def import_ceiling_check(stats):
    breaches = [f"{k}={stats[k]} (ceiling {v})" for k, v in IMPORT_CEILINGS.items()
                if stats.get(k, 0) > v]
    if breaches:
        return False, "Exceeded expected daily import volume:\n" + "\n".join(breaches)
    return True, None


def legacy_fix_ceiling_check(stats):
    total = (stats.get("renamed", 0) + stats.get("squatters_evicted", 0)
             + stats.get("payments_renamed", 0))
    if total > LEGACY_FIX_CEILING:
        return False, f"{total} rows would be renamed (ceiling {LEGACY_FIX_CEILING})"
    return True, None


def backfill_ceiling_check(stats):
    if stats.get("updated", 0) > BACKFILL_CEILING:
        return False, f"{stats['updated']} rows would update (ceiling {BACKFILL_CEILING})"
    return True, None


def main():
    tenant_id = os.environ.get("TENANT_ID")
    if not tenant_id:
        log("ERROR: TENANT_ID not set")
        sys.exit(1)
    if "DATABASE_URL" not in os.environ:
        log("ERROR: DATABASE_URL not set")
        sys.exit(1)

    lock_conn = acquire_lock()
    if lock_conn is None:
        log("Another sync run already holds the lock — skipping this tick.")
        sys.exit(0)

    prev_dir = latest_backup_dir()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if DATA_DIR.exists():
        DATA_DIR.rename(SYNC_DIR / f"data_bak_{ts}")
    DATA_DIR.mkdir()

    for stage in STAGES:
        ok, tail = run_stage(stage)
        if not ok:
            abort("ETS nightly sync FAILED — scrape stage crashed",
                  f"Stage {stage} exited non-zero. No changes were made to the "
                  f"database.\n\nLast output:\n{tail}")

    ok, reason = check_failure_rates()
    if not ok:
        abort("ETS nightly sync ABORTED — scrape failure rate too high",
              reason + "\n\nNo changes were made to the database.")

    ok, reason = check_record_drops(prev_dir)
    if not ok:
        abort("ETS nightly sync ABORTED — record count dropped unexpectedly",
              reason + "\n\nUsually means the scrape session broke partway "
              "through (auth expiry, ETS page-structure change). No changes "
              "were made to the database.")

    # Historical-bug self-heal: frees any invoice_number slot a fallback
    # (service-number) row is squatting on, so the real invoice can be
    # created. Idempotent — no-ops once caught up. Runs before the importer
    # so any newly-freed slot gets its real invoice created in this same run.
    gated_commit("legacy_number_fix", SCRIPTS_DIR / "fix_legacy_invoice_numbers.py",
                 tenant_id, legacy_fix_ceiling_check)

    gated_commit("import", SYNC_DIR / "import_to_truckpitstop.py",
                 tenant_id, import_ceiling_check, extra_args=("--parts",), needs_yes=True)

    # Defense in depth: new rows already get ets_invoiced_at / real hours set
    # at creation time by the importer above, so these should be near-empty
    # in steady state — they exist to self-heal any row ETS revised after the
    # fact (an invoice date correction, a re-billed labor line).
    gated_commit("backfill_ets_date", SCRIPTS_DIR / "backfill_invoice_ets_date.py",
                 tenant_id, backfill_ceiling_check)
    gated_commit("backfill_labor_hours", SCRIPTS_DIR / "backfill_ro_labor_hours.py",
                 tenant_id, backfill_ceiling_check)

    log("nightly sync complete")


if __name__ == "__main__":
    main()
