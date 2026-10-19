/** Arithmetic mean of the displayed revenue buckets, including zero periods. */
export function revenueAverage(amounts: number[]): number | null {
  if (amounts.length === 0) return null
  return amounts.reduce((total, amount) => total + amount, 0) / amounts.length
}
