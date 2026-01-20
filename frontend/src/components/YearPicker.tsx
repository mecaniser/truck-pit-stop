import { useMemo, useState } from 'react'

interface YearPickerProps {
  value: string
  onChange: (year: string) => void
  label?: string
  minYear?: number
  maxYear?: number
}

const DEFAULT_FIRST_YEAR = 1899

export default function YearPicker({
  value,
  onChange,
  label = 'Year',
  minYear = DEFAULT_FIRST_YEAR,
  maxYear = new Date().getFullYear(),
}: YearPickerProps) {
  const [open, setOpen] = useState(false)
  const [expanded, setExpanded] = useState(false)

  const options = useMemo(() => {
    const years: number[] = []
    for (let y = maxYear; y >= minYear; y -= 1) {
      years.push(y)
    }
    return years
  }, [maxYear, minYear])

  const gradientColor = (year: number) => {
    const idx = options.indexOf(year)
    if (idx === -1) return 'white'
    const total = Math.max(options.length - 1, 1)
    const t = idx / total
    const hue = 120 - t * 120 // green to red
    return `hsl(${hue}, 70%, 90%)`
  }

  const displayedYears = expanded ? options : options.slice(0, 27)

  return (
    <div className="relative">
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors text-left bg-white text-gray-900"
      >
        {value || 'Select year'}
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setOpen(false)} />
          <div
            className={`relative bg-white rounded-2xl shadow-2xl w-full overflow-hidden transition-all duration-300 ${
              expanded ? 'max-w-4xl' : 'max-w-md sm:max-w-lg'
            }`}
          >
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wide">Year selection</p>
                <h3 className="text-lg font-semibold text-gray-900">Choose build year</h3>
              </div>
              <button
                onClick={() => {
                  onChange('')
                  setOpen(false)
                }}
                className="text-sm text-amber-600 hover:text-amber-700"
              >
                Clear
              </button>
            </div>

            <div className="p-6">
              <div className="max-h-[60vh] overflow-y-auto sm:overflow-visible sm:max-h-none pr-2 pb-4 transition-all duration-300">
                <div
                  className={`grid gap-3 transition-all duration-300 ${
                    expanded ? 'grid-cols-4 sm:grid-cols-6' : 'grid-cols-3'
                  }`}
                >
                  {displayedYears.map((year) => (
                    <button
                      key={year}
                      type="button"
                      onClick={() => {
                        onChange(year.toString())
                        setOpen(false)
                      }}
                      className={`w-full rounded-lg px-3 py-2 text-sm font-medium border border-gray-200 transition-colors ${
                        value === year.toString()
                          ? 'ring-2 ring-amber-500 ring-offset-1'
                          : 'hover:border-amber-300 hover:bg-amber-50'
                      }`}
                      style={{ background: gradientColor(year), color: '#0f172a' }}
                    >
                      {year}
                    </button>
                  ))}
                </div>
              </div>
              {options.length > 27 && (
                <div className="mt-4 text-right">
                  <button
                    type="button"
                    onClick={() => setExpanded((prev) => !prev)}
                    className="text-sm text-amber-600 hover:text-amber-700 font-medium transition-colors"
                  >
                    {expanded ? 'Collapse' : 'Show all years'}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
