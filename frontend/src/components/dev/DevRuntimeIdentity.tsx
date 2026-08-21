type RuntimeEnvironment = {
  dev: boolean
  branch?: string
  sha?: string
}

const BRANCH_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$/
const SHA_PATTERN = /^[0-9a-f]{40}$/
const isDevelopmentBuild = import.meta.env.DEV

function runtimeIdentityLabel({ branch, sha }: Pick<RuntimeEnvironment, 'branch' | 'sha'>) {
  if (!branch || !sha || !BRANCH_PATTERN.test(branch) || !SHA_PATTERN.test(sha)) return null
  return `${branch}@${sha.slice(0, 7)}`
}

function currentEnvironment(): RuntimeEnvironment {
  const env = import.meta.env as Record<string, string | boolean | undefined>
  return {
    dev: import.meta.env.DEV,
    branch: typeof env.VITE_DIESELBRIDGE_RUNTIME_BRANCH === 'string' ? env.VITE_DIESELBRIDGE_RUNTIME_BRANCH : undefined,
    sha: typeof env.VITE_DIESELBRIDGE_RUNTIME_SHA === 'string' ? env.VITE_DIESELBRIDGE_RUNTIME_SHA : undefined,
  }
}

/** Development-only identity injected by the local runtime controller. */
export default function DevRuntimeIdentity({ environment }: { environment?: RuntimeEnvironment }) {
  if (!isDevelopmentBuild) return null

  const activeEnvironment = environment ?? currentEnvironment()
  if (!activeEnvironment.dev) return null
  const label = runtimeIdentityLabel(activeEnvironment)
  if (!label) return null

  const fullIdentity = `${activeEnvironment.branch}@${activeEnvironment.sha}`
  return (
    <span
      className="inline-flex min-w-0 max-w-24 shrink items-center truncate rounded border border-white/10 bg-white/[0.04] px-1.5 py-0.5 font-mono text-[10px] leading-4 text-slate-400 sm:max-w-44"
      aria-label={`Local development runtime: ${label}`}
      title={fullIdentity}
    >
      {label}
    </span>
  )
}
