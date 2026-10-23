"""A fake provider ledger. This module never opens a network connection."""
import hashlib
import os
from pathlib import Path
import sqlite3
from control import AcceptedProof, Refused


class FakeProvider:
    def __init__(self, path='/state/provider.sqlite3'):
        self.path=Path(path)
        if self.path.is_symlink() or self.path.resolve()!=self.path:raise Refused('fake_provider_path_refused')
        self.path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS effects(scope TEXT,kind TEXT,business_id TEXT,payload_sha256 TEXT,operation_id TEXT,receipt TEXT,PRIMARY KEY(scope,kind,business_id))')
        self.path.chmod(0o600)

    def accept(self, operation):
        with sqlite3.connect(self.path,timeout=10) as db:
            db.execute('BEGIN IMMEDIATE')
            key=tuple(operation[k] for k in ('scope','kind','business_id'))
            row=db.execute('SELECT payload_sha256,receipt FROM effects WHERE scope=? AND kind=? AND business_id=?',key).fetchone()
            if row:
                if row[0]!=operation['payload_sha256']:raise Refused('fake_provider_payload_conflict')
                return row[1]
            receipt='SIMULATION-'+hashlib.sha256((':'.join(key)+operation['payload_sha256']).encode()).hexdigest()
            db.execute('INSERT INTO effects VALUES(?,?,?,?,?,?)',(*key,operation['payload_sha256'],operation['operation_id'],receipt))
            return receipt

    def lookup(self, operation):
        with sqlite3.connect(self.path) as db:
            row=db.execute('SELECT payload_sha256,receipt FROM effects WHERE scope=? AND kind=? AND business_id=?',tuple(operation[k] for k in ('scope','kind','business_id'))).fetchone()
        if not row or row[0]!=operation['payload_sha256']:raise Refused('no_definitive_fake_acceptance_proof')
        return AcceptedProof(operation['operation_id'],operation['scope'],operation['kind'],operation['business_id'],row[0],row[1])

    def counts(self):
        with sqlite3.connect(self.path) as db:return dict(db.execute('SELECT kind,count(*) FROM effects GROUP BY kind'))
