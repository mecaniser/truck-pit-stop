"""Build a tracked source archive in an exclusive, private Docker build root."""
import argparse
import datetime
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile

ROOT = Path.home() / 'mac-hosting/test-deploy'
DOCKER = ['/Applications/Docker.app/Contents/Resources/bin/docker', '--context', 'desktop-linux']


def unpack(data, target, app):
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        total = 0
        allowed = {'backend', 'frontend'} if app == 'dieselbridge' else {'backend', 'src', 'public', 'shared', 'package.json', 'package-lock.json', 'craco.config.js', 'webpack.config.js', 'babel.config.js', 'postcss.config.js', 'tailwind.config.js', 'config-overrides.js', 'tsconfig.json', 'jsconfig.json', 'scripts'}
        for entry in archive:
            path = PurePosixPath(entry.name)
            if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] not in allowed or not (entry.isfile() or entry.isdir()):
                raise RuntimeError('Unsafe source archive member')
            if any(p in ('.git', 'node_modules', 'sessions', '__MACOSX') or p.startswith('._') for p in path.parts):
                raise RuntimeError('Unrecognized source content')
            if path.name == '.env' or path.name.startswith('.env.') or path.suffix.lower() in ('.pem', '.key', '.p12', '.pfx'):
                raise RuntimeError('Secret-shaped source path')
            total += entry.size
            if entry.size > 32 * 1024**2 or total > 256 * 1024**2:
                raise RuntimeError('Source exceeds size limit')
            destination = target.joinpath(*path.parts)
            if entry.isdir(): destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open('xb') as output: shutil.copyfileobj(archive.extractfile(entry), output)
                destination.chmod(0o700 if entry.mode & 0o111 else 0o600)


def cleanup_artifact_probe(cid_file, name, image, release):
    cid = None
    if cid_file.exists():
        if cid_file.is_symlink() or cid_file.stat().st_size > 128:
            raise RuntimeError('Unsafe artifact probe CID file')
        cid = cid_file.read_text().strip()
        if not re.fullmatch('[a-f0-9]{64}', cid): raise RuntimeError('Invalid artifact probe CID')
        filters = ['--filter', 'id=' + cid]
    else:
        filters = ['--filter', 'name=^/' + name + '$', '--filter', 'label=io.macapps.owner=macapps-test-deploy-v1',
                   '--filter', 'label=io.macapps.probe=' + release]
    found = subprocess.check_output([*DOCKER, 'ps', '-aq', '--no-trunc', *filters], timeout=15, text=True).split()
    if not found: return
    if len(found) != 1 or not re.fullmatch('[a-f0-9]{64}', found[0]) or (cid and cid != found[0]):
        raise RuntimeError('Artifact probe identity mismatch')
    cid = found[0]
    objects = json.loads(subprocess.check_output([*DOCKER, 'inspect', cid], timeout=15))
    if len(objects) != 1: raise RuntimeError('Artifact probe inspect mismatch')
    item = objects[0]; labels = item.get('Config', {}).get('Labels') or {}
    if item.get('Id') != cid or item.get('Name') != '/' + name or item.get('Image') != image or labels.get('io.macapps.owner') != 'macapps-test-deploy-v1' or labels.get('io.macapps.probe') != release:
        raise RuntimeError('Artifact probe ownership mismatch')
    if item.get('State', {}).get('Running') is True:
        subprocess.run([*DOCKER, 'rm', '-f', cid], capture_output=True, check=True, timeout=20)


def main():
    os.umask(0o077)
    os.environ['PATH'] = '/Applications/Docker.app/Contents/Resources/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin'
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('app', choices=('dieselbridge', 'tph')); p.add_argument('source'); p.add_argument('release')
    args = p.parse_args()
    if not re.fullmatch('[a-f0-9]{40}', args.source) or not re.fullmatch('[a-f0-9]{32}', args.release):
        raise RuntimeError('Invalid build identity')
    if ROOT.is_symlink() or ROOT.resolve() != ROOT or (ROOT / '.owner').read_text() != 'macapps-test-deploy-v1\n':
        raise RuntimeError('Unknown deploy root')
    tools = ROOT / 'tools'
    if tools.is_symlink() or any(p.is_symlink() for p in tools.rglob('*')):
        raise RuntimeError('Unsafe trusted adapter root')
    with (ROOT / 'private/build.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        release = ROOT / 'releases' / args.release
        release.mkdir(mode=0o700)
        context = release / 'source'; context.mkdir(mode=0o700)
        data = sys.stdin.buffer.read(280 * 1024**2)
        if len(data) >= 280 * 1024**2: raise RuntimeError('Archive exceeds size limit')
        unpack(data, context, args.app)
        names = ['Dockerfile.' + args.app]
        if args.app == 'tph': names += ['tph-web.cjs', 'tph-worker.cjs', 'tph-seed.cjs', 'tph-probe.cjs', 'public-host.cjs']
        hashes = {}
        for name in names:
            value = (tools / name).read_bytes(); hashes[name] = hashlib.sha256(value).hexdigest()
            (context / name).write_bytes(value)
        bundle = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
        metadata = {'app': args.app, 'source': args.source, 'release': args.release,
                    'archive_sha256': hashlib.sha256(data).hexdigest(), 'adapter_sha256': hashes,
                    'bundle_sha256': bundle, 'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        (release / 'build.json').write_text(json.dumps(metadata, indent=2))
        tag = 'macapps-test-deploy-' + args.app + ':' + args.release
        command = [*DOCKER, 'build', '--pull=false', '--memory=3g', '--label', 'io.macapps.owner=macapps-test-deploy-v1',
                   '--label', 'io.macapps.app=' + args.app, '--label', 'io.macapps.source=' + args.source,
                   '--label', 'io.macapps.adapters=v1', '--label', 'io.macapps.bundle-sha256=' + bundle,
                   '--build-arg', 'RAILWAY_GIT_COMMIT_SHA=' + args.source, '-f', 'Dockerfile.' + args.app, '-t', tag, '.']
        cached = None
        # Reuse only a completed, artifact-verified build of these exact bytes.
        # This also keeps separately approved database manifests bound to an image.
        for receipt in sorted((ROOT / 'releases').glob('*/build-completed.json'), reverse=True):
            if receipt.is_symlink(): raise RuntimeError('Unsafe build receipt path')
            previous = json.loads(receipt.read_text())
            if all(previous.get(k) == metadata.get(k) for k in ('app', 'source', 'archive_sha256', 'bundle_sha256')) and previous.get('artifact_verified'):
                inspected = subprocess.run([*DOCKER, 'image', 'inspect', previous['image']], capture_output=True, timeout=20)
                if inspected.returncode == 0:
                    candidate = json.loads(inspected.stdout)[0]; labels = candidate['Config'].get('Labels') or {}
                    expected = {'io.macapps.owner': 'macapps-test-deploy-v1', 'io.macapps.app': args.app,
                                'io.macapps.source': args.source, 'io.macapps.adapters': 'v1', 'io.macapps.bundle-sha256': bundle}
                    if candidate['Id'] == previous['image'] and all(labels.get(k) == v for k,v in expected.items()):
                        cached = candidate; metadata['reused_build_release'] = previous['release']; break
        if cached is None:
            with (release / 'build.log').open('xb') as log:
                subprocess.run(command, cwd=context, stdout=log, stderr=log, check=True, timeout=1800)
            image = json.loads(subprocess.check_output([*DOCKER, 'image', 'inspect', tag]))[0]
        else:
            image = cached
            (release / 'build.log').write_text('Reused exact-source, exact-adapter, artifact-verified local image.\n')
        if image['Architecture'] != 'arm64' or image['Os'] != 'linux' or not re.fullmatch(r'sha256:[a-f0-9]{64}', image['Id']):
            raise RuntimeError('Build did not produce expected ARM64 image')
        if args.app == 'dieselbridge':
            proof = ['python', '-c', "import json,shutil;from pathlib import Path;assert shutil.which('curl');s=json.loads(Path('/app/frontend/dist/build-version.json').read_text());print(json.dumps({'source':s.get('sha'),'healthcheck_tool':True}))"]
        else:
            proof = ['node', '-e', "const fs=require('fs');if(!fs.existsSync('/usr/src/app/build/index.html')||!fs.readFileSync('/usr/src/app/backend/server.js','utf8').includes(\"origin === 'https://tph-test.elisprotech.com'\"))process.exit(1);console.log(JSON.stringify({frontend:true,exact_test_origin:true}))"]
        cid_file = release / 'artifact-probe.cid'
        probe_name = 'macapps-build-probe-' + args.release
        try:
            result = subprocess.check_output([*DOCKER, 'run', '--rm', '--cidfile', str(cid_file), '--name', probe_name,
                '--label', 'io.macapps.owner=macapps-test-deploy-v1', '--label', 'io.macapps.probe=' + args.release, '--network', 'none', '--read-only',
                '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--memory', '256m',
                '--cpus', '0.5', '--pids-limit', '64', '--entrypoint', proof[0], image['Id'], *proof[1:]], timeout=30)
            artifact = json.loads(result)
            if args.app == 'dieselbridge' and artifact.get('source') != args.source:
                raise RuntimeError('Frontend build stamp does not match requested source')
        finally:
            cleanup_artifact_probe(cid_file, probe_name, image['Id'], args.release)
        metadata['artifact_verified'] = artifact
        metadata.update(image=image['Id'], completed_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        (release / 'build-completed.json').write_text(json.dumps(metadata, indent=2))
        print(json.dumps(metadata))


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('Mac test build failed: ' + type(error).__name__ + '; inspect private release log', file=sys.stderr)
        raise SystemExit(1)
