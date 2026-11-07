import { render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import App from './App'

afterEach(() => vi.unstubAllGlobals())

test('shows API health status', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => Response.json({ status: 'ok', database: 'ok' })),
  )
  render(<App />)
  expect(await screen.findByTestId('health-status')).toHaveTextContent('ok')
})
