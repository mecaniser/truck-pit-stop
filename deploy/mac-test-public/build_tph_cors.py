"""Apply only the CORS adapter to the verified, already-built public web image."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path.home() / 'mac-hosting/test-public'
CONTEXT = Path.home() / 'mac-hosting/test-stacks/builds/tph'
DOCKER = ['/Applications/Docker.app/Contents/Resources/bin/docker', '--context', 'desktop-linux']
EXPECTED = 'sha256:7b25bcd8c6688cf695ffed53f067e16528184b9a60e954d4d72121477f9d8690'
ALIAS = 'macapps-tph-public-base:' + EXPECTED.split(':')[1]
RESULT = 'tph-local-test-public-cors-accepted:b369e9f5'


def image_id(value):
    return subprocess.check_output([*DOCKER, 'image', 'inspect', value, '--format', '{{.Id}}'], text=True).strip()


def main():
    os.umask(0o077)
    if ROOT.resolve() != ROOT or (ROOT / '.owner').read_text() != 'macapps-test-public-v1\n':
        raise RuntimeError('Unrecognized public test build root')
    with (ROOT / 'private/build.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if image_id(EXPECTED) != EXPECTED:
            raise RuntimeError('Accepted base image identity mismatch')
        existing = subprocess.run([*DOCKER, 'image', 'inspect', ALIAS, '--format', '{{.Id}}'],
                                  capture_output=True, text=True)
        if existing.returncode == 0 and existing.stdout.strip() != EXPECTED:
            raise RuntimeError('Build alias belongs to a different image')
        subprocess.run([*DOCKER, 'tag', EXPECTED, ALIAS], check=True)
        if image_id(ALIAS) != EXPECTED:
            raise RuntimeError('Build alias identity mismatch')
        with (ROOT / 'private/cors-overlay-build.log').open('w') as log:
            subprocess.run([*DOCKER, 'build', '--pull=false', '-f', 'Dockerfile.public-cors',
                            '-t', RESULT, '.'], cwd=CONTEXT, stdout=log, stderr=log, check=True)
        if image_id(ALIAS) != EXPECTED:
            raise RuntimeError('Build alias changed during build')
        result = image_id(RESULT)
        receipt = {'base_image': EXPECTED, 'verified_local_alias': ALIAS, 'result_image': result,
                   'source_sha256': {name: hashlib.sha256((CONTEXT / name).read_bytes()).hexdigest()
                                     for name in ('Dockerfile.public-cors', 'public-host.cjs')}}
        (ROOT / 'private/cors-overlay-build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(receipt))


if __name__ == '__main__':
    main()
