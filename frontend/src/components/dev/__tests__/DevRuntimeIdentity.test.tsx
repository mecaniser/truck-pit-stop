import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import DevRuntimeIdentity from '../DevRuntimeIdentity'

const branch = 'codex/db037-local-runtime-controller'
const sha = 'f938398c52caf77fd29cc07c0aa8a34f5595b94d'

describe('DevRuntimeIdentity', () => {
  it('renders the validated branch and short SHA with the full identity in its title', () => {
    render(<DevRuntimeIdentity environment={{ dev: true, branch, sha }} />)

    const identity = screen.getByLabelText(`Local development runtime: ${branch}@f938398`)
    expect(identity).toHaveTextContent(`${branch}@f938398`)
    expect(identity).toHaveAttribute('title', `${branch}@${sha}`)
    expect(identity).toHaveClass('truncate')
  })

  it('omits invalid, incomplete, and production identities', () => {
    const { rerender } = render(<DevRuntimeIdentity environment={{ dev: false, branch, sha }} />)
    expect(screen.queryByLabelText(/Local development runtime/)).not.toBeInTheDocument()

    rerender(<DevRuntimeIdentity environment={{ dev: true, branch, sha: 'not-a-full-sha' }} />)
    expect(screen.queryByLabelText(/Local development runtime/)).not.toBeInTheDocument()
    rerender(<DevRuntimeIdentity environment={{ dev: true, branch }} />)
    expect(screen.queryByLabelText(/Local development runtime/)).not.toBeInTheDocument()
  })
})
