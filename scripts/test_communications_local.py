"""Focused safety tests for the explicit local-only harness."""
import ast
import asyncio
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

import communications_local as launcher

class LocalHarnessTests(unittest.TestCase):
    def test_environment_does_not_inherit_provider_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(launcher,'ROOT',root), patch.object(launcher,'CONFIG',root/'.env.communications.local'), patch.dict(os.environ,{'TWILIO_ACCOUNT_SID':'ACreal','STRIPE_SECRET_KEY':'live-value','DATABASE_URL':'postgresql://remote/prod'}):
                env = launcher.environment()
                self.assertEqual(env['TWILIO_ACCOUNT_SID'],'')
                self.assertNotIn('STRIPE_SECRET_KEY',env)
                self.assertIn('@127.0.0.1:55460/communications_local',env['DATABASE_URL'])
                self.assertEqual(env['TWILIO_AUTH_TOKEN'],env['LOCAL_WEBHOOK_SECRET'])
                self.assertEqual((launcher.CONFIG.stat().st_mode & 0o777),0o600)

    def test_existing_backend_env_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'backend').mkdir()
            (root/'backend/.env').write_text('DATABASE_URL=production')
            with patch.object(launcher,'ROOT',root), self.assertRaises(RuntimeError):
                launcher.environment()

    def test_production_environment_refuses_simulation_before_app_import(self):
        env = launcher.environment()
        env['ENVIRONMENT'] = 'production'
        env['PYTHONPATH'] = str(launcher.ROOT/'scripts') + os.pathsep + str(launcher.ROOT/'backend')
        result = subprocess.run([sys.executable, '-c', 'import communications_local_app'], env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Simulation is permitted only in explicit local development', result.stderr)

    def test_simulation_control_consumed_once_and_calls_durable(self):
        # Execute the unchanged adapter AST without importing the live application.
        tree=ast.parse((Path(__file__).parent/'communications_local_app.py').read_text())
        adapter=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='SimulatedSMSSender')
        with tempfile.TemporaryDirectory() as temp:
            ledger=Path(temp)/'calls.sqlite'
            namespace={'sqlite3':sqlite3,'uuid':uuid,'LEDGER':ledger}
            exec(compile(ast.Module(body=[adapter],type_ignores=[]),'<adapter>','exec'),namespace)
            sender=namespace['SimulatedSMSSender']()
            async def send():
                return await sender.send(body='synthetic',from_number='test',to_number='test',status_callback='local')
            with sqlite3.connect(ledger) as db:
                db.execute('CREATE TABLE control (id INTEGER PRIMARY KEY, outcome TEXT NOT NULL)')
                db.execute("INSERT INTO control VALUES (1,'unknown')")
            with self.assertRaises(TimeoutError):
                asyncio.run(send())
            self.assertEqual(asyncio.run(send())['status'],'queued')
            with sqlite3.connect(ledger) as db:
                self.assertEqual(db.execute('SELECT outcome FROM calls ORDER BY rowid').fetchall(),[('unknown',),('accepted',)])
                self.assertEqual(db.execute('SELECT COUNT(*) FROM control').fetchone()[0],0)

if __name__=='__main__':
    unittest.main()
