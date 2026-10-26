"""Opt-in bounded worker diagnostics; no exception or provider values escape."""

import json
import math
import signal
import subprocess

STAGES = frozenset({'startup', 'recovery', 'collection', 'import', 'complete'})
SIGNALS = {int(value): value.name for value in (signal.SIGTERM, signal.SIGINT, signal.SIGKILL, signal.SIGABRT, signal.SIGSEGV)}


class FuelLifecycle:
    def __init__(self, *, commit_enabled=False):
        self.commit_enabled = commit_enabled is True
        self.recovery_outcome = 'not_started'
        self.stage = 'startup'
        self.recovery_started = False
        self.new_import_started = False

    def emit(self, event, **values):
        if event not in {'stage_started', 'recovery_attempt_started', 'recovery_verified', 'child_outcome', 'worker_outcome', 'shutdown_requested'}:
            return
        payload = {
            'stage': 'fuel_lifecycle', 'event': event,
            'phase': self.stage if self.stage in STAGES else 'startup',
            'commit_enabled': self.commit_enabled,
            'recovery_outcome': self.recovery_outcome,
            'recovery_started': self.recovery_started,
            'new_import_started': self.new_import_started,
            'import_outcome': ('unknown' if self.new_import_started and self.stage != 'complete'
                               else 'runner_completed' if self.stage == 'complete' else 'not_started'),
        }
        for key in ('elapsed_ms', 'exit_code'):
            if type(values.get(key)) is int and 0 <= values[key] <= (3600000 if key == 'elapsed_ms' else 255):
                payload[key] = values[key]
        if values.get('signal') in {*SIGNALS.values(), 'other'}:
            payload['signal'] = values['signal']
        if values.get('outcome') in {'timeout', 'spawn_error', 'success', 'child_signal', 'nonzero_exit', 'unknown_failure', 'os_error'}:
            payload['outcome'] = values['outcome']
        try:
            print(json.dumps(payload), flush=True)
        except OSError:
            pass  # A diagnostic sink cannot change recovery/import decisions.

    def enter(self, stage):
        if stage not in STAGES:
            raise ValueError('Invalid lifecycle stage')
        self.stage = stage
        if stage == 'import':
            self.new_import_started = True
        self.emit('stage_started')

    def recovery_attempt(self):
        self.recovery_started = True
        self.recovery_outcome = 'unknown'
        self.emit('recovery_attempt_started')

    def recovery_verified(self):
        self.recovery_outcome = 'verified'
        self.emit('recovery_verified')

    def child_result(self, result=None, error=None, elapsed_ms=None):
        fields = {}
        if isinstance(elapsed_ms, (int, float)) and math.isfinite(elapsed_ms):
            fields['elapsed_ms'] = min(3600000, max(0, int(elapsed_ms)))
        if isinstance(error, subprocess.TimeoutExpired):
            fields['outcome'] = 'timeout'
        elif isinstance(error, OSError):
            fields['outcome'] = 'spawn_error'
        elif isinstance(result, int):
            fields['outcome'] = 'success' if result == 0 else 'child_signal' if result < 0 else 'nonzero_exit'
            if result < 0:
                fields['signal'] = SIGNALS.get(-result, 'other')
            else:
                fields['exit_code'] = min(255, result)
        else:
            fields['outcome'] = 'unknown_failure'
        self.emit('child_outcome', **fields)

    def failed(self, error):
        if isinstance(error, subprocess.CalledProcessError):
            self.child_result(result=error.returncode)
        elif isinstance(error, subprocess.TimeoutExpired):
            self.child_result(error=error)
        elif isinstance(error, OSError):
            self.emit('worker_outcome', outcome='os_error')
        else:
            self.emit('worker_outcome', outcome='unknown_failure')

    def shutdown(self, signum):
        self.emit('shutdown_requested', signal=SIGNALS.get(signum, 'other'))
