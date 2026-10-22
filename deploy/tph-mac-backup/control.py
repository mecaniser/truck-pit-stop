"""Durable single-writer control for synthetic TPH backup rehearsals only.

This module opens no network connection and cannot activate a live service.
Host-controller proof callbacks must perform their own bounded fresh observations;
they must not call this Control again while its write transaction is held.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid

ROOT = Path.home() / 'mac-hosting/tph-backup-rehearsal'
SITES = frozenset(('railway-simulation', 'mac-backup'))
KINDS = frozenset(('payment', 'email', 'sms', 'job'))


class Refused(RuntimeError):
    pass


def require(value, reason):
    if not value:
        raise Refused(reason)


def text(value, limit=128):
    require(isinstance(value, str) and 0 < len(value) <= limit and not any(ord(char) < 32 for char in value),
            'invalid_identifier')
    return value


def payload_hash(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    require(len(encoded) <= 65536, 'payload_too_large')
    return hashlib.sha256(encoded).hexdigest()


def instance(value):
    require(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None,
            'full_container_id_required')
    return value


@dataclass(frozen=True)
class StoppedProof:
    instance_id: str
    observation_id: str


@dataclass(frozen=True)
class DataProof:
    authority_id: str
    watermark: int
    target_site: str
    target_instance_id: str
    data_digest: str


@dataclass(frozen=True)
class AcceptedProof:
    operation_id: str
    scope: str
    kind: str
    business_id: str
    payload_sha256: str
    provider_receipt: str


class Control:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else ROOT / 'private/control.sqlite3'
        require(self.path.resolve() == self.path and not self.path.is_symlink(), 'control_path_refused')
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        require(self.path.parent.stat().st_uid == os.getuid()
                and not self.path.parent.stat().st_mode & 0o077, 'private_control_directory_required')
        if self.path.exists():
            require(self.path.stat().st_uid == os.getuid() and self.path.stat().st_nlink == 1,
                    'control_file_owner_refused')
        # SQLite applies these permissions to its journal/WAL files too.
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.fchmod(descriptor, 0o600)
        os.close(descriptor)
        with self._connection() as connection:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.executescript('''
              CREATE TABLE IF NOT EXISTS authority (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1), site TEXT NOT NULL,
                epoch INTEGER NOT NULL, phase TEXT NOT NULL CHECK(phase IN ('active','draining','frozen')),
                instance_id TEXT NOT NULL, authority_id TEXT NOT NULL, watermark INTEGER NOT NULL DEFAULT 0,
                transition_id TEXT, reason TEXT NOT NULL DEFAULT '');
              CREATE TABLE IF NOT EXISTS admissions (
                admission_id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, payload_sha256 TEXT NOT NULL,
                site TEXT NOT NULL, epoch INTEGER NOT NULL, instance_id TEXT NOT NULL,
                outcome TEXT NOT NULL CHECK(outcome IN ('pending','accepted','rejected','unknown')),
                created REAL NOT NULL, updated REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS operations (
                operation_id TEXT PRIMARY KEY, scope TEXT NOT NULL, kind TEXT NOT NULL,
                business_id TEXT NOT NULL, payload_sha256 TEXT NOT NULL, site TEXT NOT NULL,
                epoch INTEGER NOT NULL, instance_id TEXT NOT NULL,
                admission_id TEXT REFERENCES admissions(admission_id),
                outcome TEXT NOT NULL CHECK(outcome IN ('dispatching','accepted','rejected','unknown')),
                provider_receipt TEXT, created REAL NOT NULL, updated REAL NOT NULL,
                UNIQUE(scope,kind,business_id));
              CREATE TABLE IF NOT EXISTS transitions (
                transition_id TEXT PRIMARY KEY, old_site TEXT NOT NULL, old_epoch INTEGER NOT NULL,
                expected_old_instance_id TEXT NOT NULL, target_site TEXT, target_instance_id TEXT,
                outcome TEXT NOT NULL, stopped_observation_id TEXT, data_digest TEXT,
                authority_id TEXT NOT NULL, watermark INTEGER NOT NULL, created REAL NOT NULL);
            ''')

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=10000')
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _write(self):
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def _state(self, connection):
        row = connection.execute('SELECT * FROM authority WHERE singleton=1').fetchone()
        require(row is not None, 'control_not_initialized')
        return dict(row)

    def _fence(self, connection, site, epoch):
        state = self._state(connection)
        require(site in SITES and type(epoch) is int and state['site'] == site and state['epoch'] == epoch,
                'stale_or_wrong_writer')
        require(state['phase'] == 'active', 'writer_not_active')
        return state

    def initialize(self, site, instance_id, *, authority_id):
        require(site in SITES, 'unknown_site')
        instance(instance_id)
        text(authority_id)
        with self._write() as connection:
            require(connection.execute('SELECT count(*) FROM authority').fetchone()[0] == 0,
                    'control_already_initialized')
            connection.execute('INSERT INTO authority(singleton,site,epoch,phase,instance_id,authority_id) '
                               'VALUES(1,?,1,\'active\',?,?)', (site, instance_id, authority_id))
            return self._state(connection)

    def state(self):
        with self._connection() as connection:
            return self._state(connection)

    def _pending(self, connection):
        values = {
            'admissions_pending': connection.execute("SELECT count(*) FROM admissions WHERE outcome='pending'").fetchone()[0],
            'admissions_unknown': connection.execute("SELECT count(*) FROM admissions WHERE outcome='unknown'").fetchone()[0],
            'effects_dispatching': connection.execute("SELECT count(*) FROM operations WHERE outcome='dispatching'").fetchone()[0],
            'effects_unknown': connection.execute("SELECT count(*) FROM operations WHERE outcome='unknown'").fetchone()[0],
        }
        return {**values, 'blocked': any(values.values())}

    def pending(self):
        """Read only. Call after begin_drain and before stopping the old host."""
        with self._connection() as connection:
            connection.execute('BEGIN')
            self._state(connection)
            return self._pending(connection)

    def summary(self):
        with self._connection() as connection:
            connection.execute('BEGIN')
            state = self._state(connection)
            return {**state, 'pending': self._pending(connection),
                    'admissions': {row['outcome']: row['n'] for row in connection.execute(
                        'SELECT outcome,count(*) AS n FROM admissions GROUP BY outcome')},
                    'effects': {row['outcome']: row['n'] for row in connection.execute(
                        'SELECT outcome,count(*) AS n FROM operations GROUP BY outcome')}}

    def admit(self, site, epoch, request_id, payload=None):
        text(request_id)
        hashed = payload_hash(payload)
        with self._write() as connection:
            state = self._fence(connection, site, epoch)
            row = connection.execute('SELECT * FROM admissions WHERE request_id=?', (request_id,)).fetchone()
            if row:
                require(row['payload_sha256'] == hashed, 'request_payload_conflict')
                return {**dict(row), 'dispatch': False}
            identifier, now = uuid.uuid4().hex, time.time()
            connection.execute('INSERT INTO admissions VALUES(?,?,?,?,?,?,?,?,?)',
                (identifier, request_id, hashed, site, epoch, state['instance_id'], 'pending', now, now))
            row = connection.execute('SELECT * FROM admissions WHERE admission_id=?', (identifier,)).fetchone()
            return {**dict(row), 'dispatch': True}

    def complete(self, admission_id, outcome):
        require(outcome in ('accepted', 'rejected', 'unknown'), 'invalid_admission_outcome')
        with self._write() as connection:
            row = connection.execute('SELECT * FROM admissions WHERE admission_id=?', (admission_id,)).fetchone()
            require(row is not None, 'unknown_admission')
            if row['outcome'] != 'pending':
                require(row['outcome'] == outcome, 'admission_outcome_immutable')
                return {**dict(row), 'watermark': self._state(connection)['watermark']}
            connection.execute('UPDATE admissions SET outcome=?,updated=? WHERE admission_id=?',
                               (outcome, time.time(), admission_id))
            if outcome == 'accepted':
                connection.execute('UPDATE authority SET watermark=watermark+1 WHERE singleton=1')
            if outcome == 'unknown':
                connection.execute("UPDATE authority SET phase='frozen',reason='unknown_admission' WHERE singleton=1")
            return {**dict(row), 'outcome': outcome, 'watermark': self._state(connection)['watermark']}

    def claim_operation(self, site, epoch, kind, business_id, payload, *, scope='synthetic', admission_id=None):
        require(kind in KINDS, 'unsupported_synthetic_effect_kind')
        text(business_id)
        text(scope)
        hashed = payload_hash(payload)
        with self._write() as connection:
            state = self._fence(connection, site, epoch)
            if admission_id is not None:
                admitted = connection.execute('SELECT * FROM admissions WHERE admission_id=?', (admission_id,)).fetchone()
                require(admitted is not None and admitted['site'] == site and admitted['epoch'] == epoch
                        and admitted['outcome'] == 'pending', 'operation_admission_refused')
            row = connection.execute('SELECT * FROM operations WHERE scope=? AND kind=? AND business_id=?',
                                     (scope, kind, business_id)).fetchone()
            if row:
                require(row['payload_sha256'] == hashed, 'operation_payload_conflict')
                return {**dict(row), 'dispatch': False}
            identifier, now = uuid.uuid4().hex, time.time()
            connection.execute('INSERT INTO operations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (identifier, scope, kind, business_id, hashed, site, epoch, state['instance_id'], admission_id,
                 'dispatching', None, now, now))
            row = connection.execute('SELECT * FROM operations WHERE operation_id=?', (identifier,)).fetchone()
            return {**dict(row), 'dispatch': True}

    def authorize_dispatch(self, operation_id, site, epoch):
        with self._write() as connection:
            self._fence(connection, site, epoch)
            row = connection.execute('SELECT * FROM operations WHERE operation_id=?', (operation_id,)).fetchone()
            require(row is not None and row['site'] == site and row['epoch'] == epoch
                    and row['outcome'] == 'dispatching', 'operation_dispatch_refused')
            return dict(row)

    def complete_operation(self, operation_id, outcome, provider_receipt=None):
        require(outcome in ('accepted', 'rejected', 'unknown'), 'invalid_operation_outcome')
        if outcome == 'accepted':
            text(provider_receipt, 256)
        else:
            require(provider_receipt is None, 'unexpected_provider_receipt')
        with self._write() as connection:
            row = connection.execute('SELECT * FROM operations WHERE operation_id=?', (operation_id,)).fetchone()
            require(row is not None, 'unknown_operation')
            if row['outcome'] != 'dispatching':
                require(row['outcome'] == outcome and row['provider_receipt'] == provider_receipt,
                        'operation_outcome_immutable_requires_reconciliation')
                return {**dict(row), 'watermark': self._state(connection)['watermark']}
            connection.execute('UPDATE operations SET outcome=?,provider_receipt=?,updated=? WHERE operation_id=?',
                               (outcome, provider_receipt, time.time(), operation_id))
            if outcome == 'accepted':
                connection.execute('UPDATE authority SET watermark=watermark+1 WHERE singleton=1')
            if outcome == 'unknown':
                connection.execute("UPDATE authority SET phase='frozen',reason='unknown_operation' WHERE singleton=1")
            return {**dict(row), 'outcome': outcome, 'provider_receipt': provider_receipt,
                    'watermark': self._state(connection)['watermark']}

    def reconcile_operation(self, operation_id, verify_accepted):
        require(callable(verify_accepted), 'read_only_reconciliation_callback_required')
        with self._write() as connection:
            row = connection.execute('SELECT * FROM operations WHERE operation_id=?', (operation_id,)).fetchone()
            require(row is not None, 'unknown_operation')
            if row['outcome'] == 'accepted':
                return {**dict(row), 'watermark': self._state(connection)['watermark']}
            require(row['outcome'] in ('unknown', 'dispatching'), 'operation_not_reconcilable')
            proof = verify_accepted(dict(row))
            require(isinstance(proof, AcceptedProof), 'definitive_accepted_proof_required')
            require(all(getattr(proof, key) == row[key] for key in
                        ('operation_id', 'scope', 'kind', 'business_id', 'payload_sha256')),
                    'reconciliation_proof_mismatch')
            text(proof.provider_receipt, 256)
            connection.execute("UPDATE operations SET outcome='accepted',provider_receipt=?,updated=? WHERE operation_id=?",
                               (proof.provider_receipt, time.time(), operation_id))
            connection.execute('UPDATE authority SET watermark=watermark+1 WHERE singleton=1')
            return {**dict(row), 'outcome': 'accepted', 'provider_receipt': proof.provider_receipt,
                    'watermark': self._state(connection)['watermark']}

    def freeze(self, reason='operator_freeze'):
        text(reason)
        with self._write() as connection:
            self._state(connection)
            connection.execute("UPDATE authority SET phase='frozen',reason=? WHERE singleton=1", (reason,))
            return self._state(connection)

    def begin_drain(self, site, epoch):
        with self._write() as connection:
            state = self._state(connection)
            require(site in SITES and type(epoch) is int and state['site'] == site and state['epoch'] == epoch,
                    'stale_or_wrong_writer')
            identifier = state['transition_id'] or uuid.uuid4().hex
            if state['transition_id'] is None:
                connection.execute('INSERT INTO transitions(transition_id,old_site,old_epoch,expected_old_instance_id,'
                    'outcome,authority_id,watermark,created) VALUES(?,?,?,?,?,?,?,?)',
                    (identifier, site, epoch, state['instance_id'], 'draining', state['authority_id'], state['watermark'], time.time()))
            connection.execute("UPDATE authority SET phase='draining',transition_id=?,reason='' WHERE singleton=1", (identifier,))
            return dict(connection.execute('SELECT * FROM transitions WHERE transition_id=?', (identifier,)).fetchone())

    def promote(self, target_site, target_instance_id, verify_stopped, verify_data):
        require(target_site in SITES, 'unknown_site')
        instance(target_instance_id)
        require(callable(verify_stopped) and callable(verify_data), 'host_proof_callbacks_required')
        with self._write() as connection:
            state = self._state(connection)
            require(state['phase'] == 'draining' and state['transition_id'] is not None, 'drain_required')
            require(target_site != state['site'] and target_instance_id != state['instance_id'], 'different_target_required')
            pending = connection.execute("SELECT count(*) FROM admissions WHERE outcome IN ('pending','unknown')").fetchone()[0]
            effects = connection.execute("SELECT count(*) FROM operations WHERE outcome IN ('dispatching','unknown')").fetchone()[0]
            require(pending == 0 and effects == 0, 'inflight_or_unknown_blocks_transfer')
            transition = connection.execute('SELECT * FROM transitions WHERE transition_id=?', (state['transition_id'],)).fetchone()
            require(transition['expected_old_instance_id'] == state['instance_id'] and transition['old_epoch'] == state['epoch'],
                    'transition_identity_mismatch')
            stopped = verify_stopped(state['instance_id'])
            require(isinstance(stopped, StoppedProof) and stopped.instance_id == state['instance_id'],
                    'exact_stopped_instance_proof_required')
            text(stopped.observation_id)
            data = verify_data(state['authority_id'], state['watermark'], target_site, target_instance_id)
            require(isinstance(data, DataProof) and data.authority_id == state['authority_id']
                    and type(data.watermark) is int and data.watermark == state['watermark']
                    and data.target_site == target_site and data.target_instance_id == target_instance_id
                    and isinstance(data.data_digest, str) and re.fullmatch(r'[0-9a-f]{64}', data.data_digest) is not None,
                    'rpo_zero_fresh_data_proof_required')
            connection.execute("UPDATE transitions SET target_site=?,target_instance_id=?,outcome='promoted',"
                'stopped_observation_id=?,data_digest=?,watermark=? WHERE transition_id=?',
                (target_site, target_instance_id, stopped.observation_id, data.data_digest, state['watermark'], state['transition_id']))
            connection.execute("UPDATE authority SET site=?,epoch=epoch+1,phase='active',instance_id=?,transition_id=NULL,reason='' WHERE singleton=1",
                               (target_site, target_instance_id))
            return self._state(connection)

    def operation(self, operation_id):
        with self._connection() as connection:
            row = connection.execute('SELECT * FROM operations WHERE operation_id=?', (operation_id,)).fetchone()
            require(row is not None, 'unknown_operation')
            return dict(row)

    def activate_live(self, *args, **kwargs):
        raise Refused('live_activation_forbidden_primary_not_fenced_no_approved_production_data_provider_domain_plan')
