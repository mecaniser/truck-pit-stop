"""Read existing synthetic rows only; never enqueue or authenticate a provider."""
import json
from pathlib import Path
import rollout


def main():
    rollout.safe_root()
    operator = rollout.load_operator()
    with operator.lock():
        pg = operator.compose('dieselbridge', 'exec', '-T', 'postgres', 'psql',
            '-U', 'localtest', '-d', 'dieselbridge_local_test', '-At', '-v', 'ON_ERROR_STOP=1',
            '-c', 'BEGIN READ ONLY; SELECT (SELECT count(*) FROM tenants),'
            '(SELECT count(*) FROM users),(SELECT count(*) FROM customers),'
            '(SELECT count(*) FROM local_test_receipts),'
            '(SELECT sum(execution_count) FROM local_test_receipts); COMMIT;', log='public-read-counts-pg').decode()
        counts = next(line for line in pg.splitlines() if '|' in line)
        script = """const m=require('mongoose');
(async()=>{await m.connect(process.env.MONGO_URI_DEV);
const d=m.connection.db;const job=await d.collection('blogresearchjobs').findOne({topic:'LOCALTEST: synthetic worker acceptance'});
const r={locations:await d.collection('parkingspaces').countDocuments(),pins:await d.collection('pins').countDocuments(),
jobs:await d.collection('blogresearchjobs').countDocuments(),attempts:job.attempts,status:job.status,
posts:await d.collection('blogposts').countDocuments(),published:await d.collection('blogposts').countDocuments({status:'published'}),
scheduled:await d.collection('blogresearchjobs').countDocuments({trigger:'scheduled'})};
await m.disconnect();console.log(JSON.stringify(r));process.exit(0)})().catch(()=>process.exit(1));"""
        mongo = json.loads(operator.compose('tph', 'exec', '-T', 'web', 'node', '-e', script,
                                           log='public-read-counts-mongo').decode().strip().splitlines()[-1])
    assert counts == '2|2|2|1|1'
    assert mongo == dict(locations=2, pins=1, jobs=1, attempts=1, status='completed', posts=1, published=0, scheduled=0)
    result = {'postgres': counts, 'mongo': mongo, 'read_only': True, 'worker_triggered': False}
    (rollout.ROOT / 'private/counts-after.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
