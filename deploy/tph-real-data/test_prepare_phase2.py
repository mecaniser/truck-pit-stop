import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import prepare_phase2 as phase2
import prepare


class Phase2Tests(unittest.TestCase):
    def test_role_uses_real_case_sensitive_booking_collection_and_no_queue_or_credential_reads(self):
        self.assertIn('Bookings', phase2.READ_COLLECTIONS)
        self.assertNotIn('bookings', phase2.READ_COLLECTIONS)
        self.assertFalse(set(phase2.READ_COLLECTIONS) & {'users','hiringleads','logs','blogresearchjobs','bookingsessions','bookingsessiontokens','magiclinks'})
        self.assertNotIn("actions:['insert'",phase2.role_source())
        self.assertNotIn('dbAdmin',phase2.role_source())
        self.assertIn("collection:'pins'},actions:['update']",phase2.role_source())

    def test_auth0_profile_and_no_generic_api_get_or_business_post(self):
        config=phase2.nginx()
        self.assertIn('~*^(GET|HEAD):/(?!api(?:/|$))',config)
        self.assertIn('default 0',config)
        self.assertNotIn('~^(GET|HEAD): 1',config)
        for path in ('payments','bookings/auth','send-otp','webhooks','blog-studio','create-booking'):
            self.assertNotIn('"POST:/api/'+path+'" 1',config)
        self.assertIn('https://'+phase2.DOMAIN,config)
        self.assertNotIn('*.auth0.com',config)
        self.assertIn('proxy_set_header X-Forwarded-Proto https',config)

    def test_preparation_preserves_original_mongo_and_does_not_overwrite_old_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary).resolve();root=base/'runtime';root.mkdir();source=base/'tools';source.mkdir()
            manifest={'source':prepare.SOURCE,'token':'a'*32,'images':{'web':'sha256:'+'b'*64,'mongo':'sha256:'+'c'*64,'gateway':'sha256:'+'d'*64}}
            spec=prepare.specification(manifest,root)
            raw=json.dumps(spec,sort_keys=True).encode();(root/'compose.json').write_bytes(raw)
            original={'project':spec['name'],'manifest':manifest,'artifacts_sha256':{'compose.json':phase2.digest(raw)}}
            plan=json.dumps(original).encode();(root/'plan.json').write_bytes(plan)
            for name in ('clone-web-auth0.cjs','auth0_cached_jwks.cjs','auth0-jwks.json'):(source/name).write_text('fixture')
            with patch.object(phase2,'PLAN_SHA',phase2.digest(plan)):
                result=phase2.prepare(root,source)
                self.assertFalse(result['runtime_started'])
                self.assertEqual((root/'plan.json').read_bytes(),plan)
                self.assertEqual((root/'compose.json').read_bytes(),raw)
                after=json.loads((root/'phase2-auth0/compose.json').read_text())
                self.assertEqual(after['services']['mongo'],spec['services']['mongo'])
                self.assertEqual(after['networks'],spec['networks'])
                self.assertEqual(after['volumes'],spec['volumes'])
                self.assertEqual(set(after['services']),{'mongo','web','gateway'})
                self.assertEqual(after['services']['web']['environment']['SQUARE_ACCESS_TOKEN'],'LOCAL_TEST_INVALID_NOT_A_PROVIDER_CREDENTIAL')
                self.assertEqual(after['services']['web']['environment']['DISABLE_SCHEDULER'],'true')
                self.assertEqual(after['services']['web']['networks'],['isolated'])
                self.assertFalse(json.loads((root/'phase2-auth0/plan.json').read_text())['public_cutover'])
                with self.assertRaises(AssertionError):phase2.prepare(root,source)


if __name__=='__main__':unittest.main()
