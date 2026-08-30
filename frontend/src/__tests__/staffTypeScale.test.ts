import { describe, expect, it } from 'vitest'
import STAFF_CSS from '../index.css?inline'

/**
 * Type inside the staff workspace must follow the shop's text-size setting.
 *
 * The setting moves three things, and a fourth used to be missed entirely:
 *   - inherited body text, via --theme-font-scale on .db-staff-shell
 *   - Tailwind text-* utilities, via the --db-type-* overrides
 *   - hand-written CSS, via --font-size-body
 *
 * Thirty hand-written declarations were in raw px or rem, so they stayed put
 * while everything around them grew: at Large the body text grew 12.5% and the
 * ledger names, facts and page headings did not, which compresses the hierarchy
 * the sizes exist to express.
 *
 * rem cannot work here — this stylesheet pins html to 16px, so rem ignores the
 * setting. em cannot be trusted either — it resolves against the parent's
 * computed size, and these elements sit under ledgers and Tailwind utilities
 * that set their own. A ratio of --font-size-body is inherited untouched
 * through both, so it means the same thing wherever it appears.
 */
describe('staff workspace type follows the text-size setting', () => {
  const lines = STAFF_CSS.split('\n')

  const owningSelector = (index: number): string => {
    for (let i = index; i >= 0; i -= 1) {
      if (lines[i].includes('{')) return lines[i].split('{')[0].trim()
    }
    return ''
  }

  const staffScoped = (selector: string) =>
    selector.includes('db-presentation-new') || selector.includes('db-staff')

  const frozen: string[] = []
  lines.forEach((line, index) => {
    if (!/font-size:\s*[\d.]+(rem|px)/.test(line)) return
    const selector = owningSelector(index)
    if (staffScoped(selector)) frozen.push(`${selector.slice(0, 70)} -> ${line.trim().slice(0, 50)}`)
  })

  it('sizes no staff type in raw px or rem', () => {
    expect(frozen).toEqual([])
  })

  it('still expresses the sizes it does set as a ratio of the setting', () => {
    const ratios = STAFF_CSS.match(/font-size:\s*calc\(var\(--font-size-body\)/g) ?? []
    expect(ratios.length).toBeGreaterThanOrEqual(30)
  })
})
