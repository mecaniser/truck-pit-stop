export function motiveError(error: unknown): string {
  const code = (error as { response?: { data?: { detail?: { code?: string } } } })?.response?.data?.detail?.code
  if (code === 'oauth_denied') return 'Motive connection was cancelled. Your existing connection has not been replaced.'
  if (code === 'oauth_session_invalid') return 'This connection request is invalid or expired. Start again from Integrations.'
  const status = (error as { response?: { status?: number } })?.response?.status
  if (status === 403) return 'Only an authorized company administrator can manage this connection.'
  if (status === 404) return 'This company or truck is no longer available. Refresh and try again.'
  if (status === 409) return 'The connection or truck assignment changed. Refresh before trying again.'
  if (status === 429) return 'Motive is receiving too many requests. Please try again later.'
  if (status === 424) return 'Motive access is not ready. Please try again after setup is complete.'
  if (status === 503) return 'Motive is unavailable right now. Please try again later.'
  return 'We could not complete this request. Refresh the connection and try again.'
}
