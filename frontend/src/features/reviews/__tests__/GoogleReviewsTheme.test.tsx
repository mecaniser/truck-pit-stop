import { describe, expect, it } from 'vitest'
import STAFF_CSS from '../../../index.css?inline'
import INBOX_SOURCE from '../GoogleReviewsPage.tsx?raw'
import SETTINGS_SOURCE from '../GoogleReviewsSettingsPage.tsx?raw'

/**
 * DB-081. Both Google Reviews pages were written with a night-only palette
 * (text-white, bg-white/5, border-white/10, amber-200 notices ...). Under Day
 * shop the inbox's "Google connection & settings" link, card labels and filter
 * tabs were white on the road-white canvas, and the settings page's notices and
 * fields read light-on-dark.
 *
 * The staff shell themes pages the same way everywhere else (services, team,
 * messages): the page root carries a workspace class, and index.css maps its
 * legacy dark utilities onto the tokens that flip with data-appearance-mode.
 * jsdom cannot resolve those tokens, so this guards the contract instead:
 * every night-only utility either page uses must be remapped inside the
 * reviews workspace, so a new one cannot silently reintroduce the defect.
 */
const WORKSPACE = 'db-reviews-workspace'

const NIGHT_ONLY =
  /(?<![\w-])(?:hover:)?(?:text-white|text-gray-[1-5]00|text-(?:amber|emerald|red)-[1-3]00|bg-(?:white|black)\/\d+|bg-(?:amber|emerald|red)-400\/\d+|border-white\/\d+|border-red-400\/\d+)(?![\w/-])/g

const nightOnlyUtilities = (source: string) => [...new Set(source.match(NIGHT_ONLY) ?? [])]

const reviewsRules = STAFF_CSS.split('}')
  .map(rule => rule.slice(0, rule.lastIndexOf('{')))
  .filter(selector => selector.includes('.db-presentation-new') && selector.includes(`.${WORKSPACE}`))
  .join('\n')

const selectorFor = (utility: string) => {
  const escaped = utility.replace(/[:/]/g, match => `\\${match}`)
  return utility.startsWith('hover:') ? `.${escaped}:hover` : `.${escaped}`
}

describe.each([
  ['GoogleReviewsPage', INBOX_SOURCE],
  ['GoogleReviewsSettingsPage', SETTINGS_SOURCE],
])('%s theme', (_name, source) => {
  it('renders inside the reviews workspace so the staff appearance applies', () => {
    const root = source.match(/return <div className="([^"]+)"/)
    expect(root?.[1].split(' ')).toContain(WORKSPACE)
  })

  it('maps every night-only utility onto appearance tokens', () => {
    const utilities = nightOnlyUtilities(source)
    expect(utilities.length).toBeGreaterThan(0)
    const unmapped = utilities.filter(utility => !reviewsRules.includes(selectorFor(utility)))
    expect(unmapped).toEqual([])
  })
})
