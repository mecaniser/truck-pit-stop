export function trackedTimeLabel(seconds: number | null): string {
  if (seconds === null) return 'Time not tracked'
  if (seconds === 0) return 'No tracked time'
  const total = Math.floor(seconds)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  return hours ? `${hours}h ${minutes}m tracked` : `${minutes}m ${total % 60}s tracked`
}
