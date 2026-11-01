import { ExternalLink } from 'lucide-react'

export function ImportedBillingSourceLink({ url }: { url?: string | null }) {
  // Defense in depth: never render arbitrary API-provided external destinations.
  if (!url || !/^https:\/\/easytruck\.shop\/[A-Za-z0-9_-]{1,160}\/services\/[0-9]{1,160}\/invoice$/.test(url)) return null
  return <a href={url} target="_blank" rel="noopener noreferrer"
    className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded text-xs font-semibold underline underline-offset-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-600"
    onClick={event => event.stopPropagation()}>
    Verify in ETS<ExternalLink className="h-3.5 w-3.5" aria-hidden="true" /><span className="sr-only"> (opens in a new tab)</span>
  </a>
}
