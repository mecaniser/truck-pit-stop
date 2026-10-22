"""Back up synthetic databases and restore into new private databases; never overwrite."""
import datetime
import json
from pathlib import Path
import uuid
from stackctl import ROOT, compose, lock


def main():
    with lock():
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')
        backup = ROOT/'backups'/stamp
        backup.mkdir(mode=0o700)
        pg = compose('dieselbridge','exec','-T','postgres','pg_dump','-U','localtest','-d','dieselbridge_local_test','-Fc',log='pg-dump')
        (backup/'dieselbridge.dump').write_bytes(pg)
        restore = 'local_restore_'+uuid.uuid4().hex[:12]
        compose('dieselbridge','exec','-T','postgres','createdb','-U','localtest',restore,log='pg-create-restore')
        compose('dieselbridge','exec','-T','postgres','pg_restore','-U','localtest','-d',restore,stdin=pg,log='pg-restore')
        query='SELECT (SELECT count(*) FROM tenants), (SELECT count(*) FROM users), (SELECT count(*) FROM customers), (SELECT count(*) FROM local_test_receipts)'
        counts=compose('dieselbridge','exec','-T','postgres','psql','-U','localtest','-d',restore,'-At','-c',query,log='pg-restore-count').decode().strip()
        assert counts=='2|2|2|1', 'Unexpected restored PostgreSQL counts'
        environment=dict(line.split('=',1) for line in (ROOT/'private/local.env').read_text().splitlines())
        config='/tmp/macapps-mongo-'+uuid.uuid4().hex+'.json'
        uri='mongodb://localtest:'+environment['MONGO_PASSWORD']+'@127.0.0.1:27017/?authSource=admin'
        # Credential stays in a mode0600 temporary config, never in process args.
        compose('tph','exec','-T','mongo','sh','-c','umask 077; cat > '+config,
                stdin=json.dumps({'uri':uri}).encode(),log='mongo-private-config')
        try:
            archive=compose('tph','exec','-T','mongo','mongodump','--config',config,'--archive','--db','tph_local_test',log='mongo-dump')
            (backup/'tph.archive').write_bytes(archive)
            mongo_restore='tph_restore_'+uuid.uuid4().hex[:12]
            compose('tph','exec','-T','mongo','mongorestore','--config',config,'--archive',
                    '--nsFrom','tph_local_test.*','--nsTo',mongo_restore+'.*',stdin=archive,log='mongo-restore')
        finally:
            compose('tph','exec','-T','mongo','rm','-f',config,log='mongo-private-config-cleanup')
        javascript='''const c=new Mongo('mongodb://localtest:'+process.env.MONGO_INITDB_ROOT_PASSWORD+'@127.0.0.1:27017/?authSource=admin'); const d=c.getDB('''+json.dumps(mongo_restore)+'''); print(JSON.stringify({locations:d.parkingspaces.countDocuments(),pins:d.pins.countDocuments(),jobs:d.blogresearchjobs.countDocuments(),drafts:d.blogposts.countDocuments({status:'draft'}),published:d.blogposts.countDocuments({status:'published'})}));'''
        mongo_counts=json.loads(compose('tph','exec','-T','mongo','mongosh','--quiet','--eval',javascript,log='mongo-restore-count').decode().strip().splitlines()[-1])
        assert mongo_counts=={'locations':2,'pins':1,'jobs':1,'drafts':1,'published':0}
        report={'backup_directory':str(backup),'postgres_restore_database':restore,'postgres_counts':counts,
                'mongo_restore_database':mongo_restore,'mongo_counts':mongo_counts,'primary_databases_preserved':True}
        (ROOT/'private/backup-restore-receipt.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report))


if __name__=='__main__': main()
