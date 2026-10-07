/** Relative road distance, anchored to the complete comparison set, not search results. */
export function distanceColor(miles: number, min: number, max: number): string | undefined {
  if (![miles, min, max].every(Number.isFinite) || miles < 0 || min < 0 || max < min) return undefined
  const ratio = max === min ? 0 : Math.max(0, Math.min(1, (miles - min) / (max - min)))
  const stops = [[74, 222, 128], [251, 191, 36], [248, 113, 113]]
  const segment = ratio <= .5 ? 0 : 1
  const amount = ratio <= .5 ? ratio * 2 : (ratio - .5) * 2
  const color = stops[segment].map((value, index) => Math.round(value + (stops[segment + 1][index] - value) * amount))
  return `rgb(${color.join(', ')})`
}
