#!/bin/sh
# Build exact reviewed collector source plus staging-only fixtures; no ignored files.
set -eu
# macOS tar otherwise synthesizes AppleDouble ._ files from copied xattrs.
export COPYFILE_DISABLE=1
SOURCE_SHA=576ce5a8a2c0bad7b8d33a236e6514bc448e8677
SOURCE_REPO=${1:?usage: worker-build.sh worker-source-repository [--context-only]}
MODE=${2:-build}
case "$MODE" in build|--context-only) ;; *) echo "Unknown mode" >&2; exit 2;; esac
HARNESS_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BUILD_DIR=$(mktemp -d "${TMPDIR:-/tmp}/dieselbridge-worker-build.XXXXXX")
CONTEXT_ARCHIVE="$BUILD_DIR.tar"
COMPRESSED_ARCHIVE="$CONTEXT_ARCHIVE.gz"
trap 'rm -rf "$BUILD_DIR"; rm -f "$CONTEXT_ARCHIVE" "$COMPRESSED_ARCHIVE"' EXIT HUP INT TERM
[ "$(git -C "$SOURCE_REPO" rev-parse "$SOURCE_SHA^{commit}")" = "$SOURCE_SHA" ]
git -C "$SOURCE_REPO" archive "$SOURCE_SHA" backend scripts/collect_motive_trips.mjs | tar -x -C "$BUILD_DIR"
mkdir -p "$BUILD_DIR/staging-fixture"
cp "$HARNESS_DIR"/worker-fixture.cjs "$BUILD_DIR/staging-fixture/"
cp "$HARNESS_DIR"/worker-entry.py "$BUILD_DIR/staging-fixture/"
python3 - "$BUILD_DIR/staging-fixture" <<'CHECKSUM'
import hashlib, json, pathlib, sys
root=pathlib.Path(sys.argv[1])
(root/'fixture-checksums.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.iterdir())},sort_keys=True)+'\n')
CHECKSUM
# Use source Dockerfile unchanged, adding only explicit opt-in staging entrypoint.
cat "$BUILD_DIR/backend/Dockerfile.motive-trips" > "$BUILD_DIR/Worker.Dockerfile"
cat >> "$BUILD_DIR/Worker.Dockerfile" <<DOCKER
COPY staging-fixture/ /staging-fixture/
LABEL org.opencontainers.image.revision=$SOURCE_SHA
ENV STAGING_WORKER_SOURCE_SHA=$SOURCE_SHA
ENTRYPOINT ["python", "/staging-fixture/worker-entry.py"]
DOCKER
# Exclude filesystem metadata even if an archive or tool copied it as ordinary
# files. Validate the exact emitted archive before sending a byte to Docker/SSH.
tar --exclude='._*' --exclude='.DS_Store' -C "$BUILD_DIR" -cf "$CONTEXT_ARCHIVE" .
python3 - "$CONTEXT_ARCHIVE" <<'VERIFY'
import pathlib, sys, tarfile
with tarfile.open(sys.argv[1], 'r:') as archive:
    members=archive.getmembers()
    for member in members:
        parts=pathlib.PurePosixPath(member.name).parts
        if any(part.startswith('._') or part == '.DS_Store' for part in parts):
            raise SystemExit('Refusing AppleDouble metadata in worker context')
        if member.isfile() and member.name.endswith('.py'):
            content=archive.extractfile(member).read()
            if b'\x00' in content:
                raise SystemExit('Refusing NUL bytes in Python worker source: '+member.name)
    if not any(member.name == './staging-fixture/worker-entry.py' for member in members):
        raise SystemExit('Worker launcher missing from build context')
VERIFY
if [ "$MODE" = --context-only ]; then
  cat "$CONTEXT_ARCHIVE"
  exit 0
fi
# Gzip makes Docker stdin context detection unambiguous for macOS POSIX pax tar.
gzip -c "$CONTEXT_ARCHIVE" > "$COMPRESSED_ARCHIVE"
DOCKER_BUILDKIT=1 docker build --label "org.opencontainers.image.revision=$SOURCE_SHA" -f Worker.Dockerfile -t "dieselbridge-staging-workers:$SOURCE_SHA" - < "$COMPRESSED_ARCHIVE"
