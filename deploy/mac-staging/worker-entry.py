"""Staging-only launcher; preserves real worker entrypoints and import gates."""
import os
import json
import runpy
import signal
from pathlib import Path
import sys
from urllib.parse import urlsplit

WORKERS = {
    'sync': 'scripts.motive_sync.run_worker',
    'health': 'scripts.motive_health.run_worker',
    'trips': 'scripts.motive_sync.run_trip_worker',
    'fuel': 'scripts.motive_sync.run_fuel_worker',
    'drivers': 'scripts.motive_drivers.run_fleets',
}

def main():
    url = urlsplit(os.environ.get('DATABASE_URL', ''))
    if (os.environ.get('ENVIRONMENT'), url.hostname, url.path) != (
        'staging', 'postgres', '/dieselbridge_worker_fixture'
    ):
        raise SystemExit('Refusing a non-fixture database')
    if len(sys.argv) != 2 or sys.argv[1] not in WORKERS:
        raise SystemExit('Exactly one worker required: ' + ', '.join(WORKERS))
    if os.environ.get('STAGING_WORKER_FIXTURE') != 'synthetic-v1':
        raise SystemExit('Explicit synthetic fixture opt-in required')
    if os.environ.get('MOTIVE_EMAIL') != 'fixture@example.invalid' or os.environ.get('MOTIVE_PASSWORD') != 'synthetic-not-a-provider-password':
        raise SystemExit('Dummy provider credentials required')
    if os.environ.get('NODE_OPTIONS'):
        raise SystemExit('Do not supply arbitrary Node preloads')
    state = Path('/state')
    if not state.is_dir():
        raise SystemExit('Private persistent /state mount required')
    os.environ['NODE_OPTIONS'] = '--require=/staging-fixture/worker-fixture.cjs'
    for kind in ('SYNC', 'HEALTH', 'TRIPS', 'FUEL', 'DRIVER'):
        os.environ[f'MOTIVE_{kind}_STATE_DIR'] = str(state / kind.lower())
    if os.environ.get('STAGING_DRIVER_KILL_AFTER_FIRST_VERIFIED') == 'true':
        if os.getpid() == 1:
            raise SystemExit('Journal kill probe requires docker run --init; PID 1 is protected')
        if sys.argv[1] != 'drivers' or os.environ.get('MOTIVE_DRIVER_JOURNAL') != 'database' or os.environ.get('MOTIVE_DRIVER_COMMIT') != 'true':
            raise SystemExit('Journal kill probe requires committed database driver worker')
        sys.path.insert(0, '/app')
        from scripts.motive_drivers.journal import DurableRun
        original = DurableRun.checkpoint
        marker = state / 'driver-first-fleet-verified.killed'
        if marker.exists() and (marker.is_symlink() or not marker.is_file() or marker.stat().st_mode & 0o077):
            raise SystemExit('Unsafe journal kill marker')
        async def checkpoint_then_kill(self, receipt, *, attempt=None):
            # Return from the unchanged method means its transaction committed.
            # Never fabricate a receipt, skip a guard, or interrupt inside commit.
            result = await original(self, receipt, attempt=attempt)
            if (receipt.get('stage') == 'verified' and receipt.get('committed') is True
                    and str(self.journal.identity.customer_id) == os.environ['MOTIVE_DRIVER_FLEET_CUSTOMER_ID']
                    and not marker.exists()):
                proof = {'stage': 'staging_first_fleet_verified_kill_requested',
                         'pid': os.getpid(), 'run_id': str(self.id),
                         'source_sha256': receipt.get('source_sha256')}
                fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'w') as stream:
                    json.dump(proof, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                print(json.dumps(proof), flush=True)
                os.kill(os.getpid(), signal.SIGKILL)
                # A successful self-SIGKILL never returns. Do not project another
                # fleet if namespace protection or another fault prevents it.
                print(json.dumps({'stage': 'staging_kill_probe_failed',
                                  'reason': 'SIGKILL_returned'}), flush=True)
                os._exit(70)
            return result
        DurableRun.checkpoint = checkpoint_then_kill
        runpy.run_module(WORKERS[sys.argv[1]], run_name='__main__')
        return
    os.execv(sys.executable, [sys.executable, '-m', WORKERS[sys.argv[1]]])

if __name__ == '__main__':
    main()
