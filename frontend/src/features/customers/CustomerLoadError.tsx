import { ControlButton } from '@/components/ui/Controls'
type Props = {
  subject: string
  onRetry?: () => void
  isRetrying?: boolean
}

/** Failed reads must never be presented as an empty customer record. */
export default function CustomerLoadError({ subject, onRetry, isRetrying = false }: Props) {
  return (
    <div className="db-customer-load-error" role="alert" aria-busy={isRetrying}>
      <span>Could not load {subject}.</span>
      {onRetry && <ControlButton type="button" disabled={isRetrying} onClick={onRetry}>
        {isRetrying ? 'Retrying…' : `Retry ${subject}`}
      </ControlButton>}
    </div>
  )
}
