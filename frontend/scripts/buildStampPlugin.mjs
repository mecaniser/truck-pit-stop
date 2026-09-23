/**
 * DB-076: write the build stamp the backend serves at /build-version.
 *
 * The frontend build owns this fact — only it knows the identity of the bundle
 * it just produced. The backend only reads the file. See the DB-076 contract in
 * docs/PROJECT_BOARD.md.
 *
 * This does NOT relax `isLocalRuntimeServe` in vite.config.ts. That guard stops
 * ambient VITE_* values reaching the client, and nothing here is exposed to
 * client code: the stamp is emitted as its own asset, not defined into the
 * bundle.
 */
const SHA_PATTERN = /^[0-9a-f]{40}$/

export function buildStampPlugin({ sha, now = () => new Date().toISOString() } = {}) {
  // An absent sha is a legitimate build (a local `npm run build` with no git
  // context). A malformed one is a misconfiguration worth failing on, so the
  // 40-lowercase-hex check the repo already applies is kept.
  if (sha && !SHA_PATTERN.test(sha)) {
    throw new Error('build stamp sha must be 40 lowercase hex characters')
  }
  const stamp = sha
    ? { sha, built_at: now() }
    : { sha: null, built_at: null }

  return {
    name: 'dieselbridge-build-stamp',
    generateBundle() {
      this.emitFile({
        type: 'asset',
        fileName: 'build-version.json',
        source: JSON.stringify(stamp),
      })
    },
  }
}
