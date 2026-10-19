/** Median of the weekly amounts shown in the revenue chart, including zero weeks. */
export function weeklyRevenueMedian(amounts: number[]): number | null {
  if (amounts.length === 0) return null
  const sorted = [...amounts].sort((a, b) => a - b)
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 1
    ? sorted[middle]
    : (sorted[middle - 1] + sorted[middle]) / 2
}
