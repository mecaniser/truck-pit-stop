import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

/** Choose through the visible menu; retain compatibility with native test doubles. */
export async function chooseSelectOption(
  field: HTMLElement,
  value: string,
  user: Pick<ReturnType<typeof userEvent.setup>, 'click' | 'selectOptions'> = userEvent,
) {
  const current = await waitFor(() => {
    const element = field.id ? document.getElementById(field.id) : field
    if (!element || element.matches(':disabled')) throw new Error('Dropdown is not ready')
    return element
  })
  if (current instanceof HTMLSelectElement) { await user.selectOptions(current, value); return }
  await user.click(current)
  const option = await waitFor(() => {
    const found = screen.getAllByRole('option').find(item => (item as HTMLButtonElement).value === value)
    if (!found) throw new Error(`Dropdown option ${JSON.stringify(value)} is unavailable`)
    return found
  })
  await user.click(option)
}
