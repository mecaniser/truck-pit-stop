interface InvoiceReviewLinkProps {
  url?: string | null
  className?: string
}

export default function InvoiceReviewLink({ url, className = '' }: InvoiceReviewLinkProps) {
  if (!url) return null
  try {
    const parsed = new URL(url)
    if (parsed.protocol !== 'https:' || parsed.username || parsed.password) return null
  } catch {
    return null
  }
  return (
    <p className={`text-center text-sm ${className}`}>
      Share your experience:{' '}
      <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center font-medium underline underline-offset-4">
        Leave a review
      </a>
    </p>
  )
}
