import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AddressIntakePage } from './AddressIntakePage'
import { apiError, renderWithProviders, stubFetch } from '../test/utils'
import type { StubRoute } from '../test/utils'

const CASE = {
  match: 'GET /api/v1/cases/c1',
  body: {
    id: 'c1',
    case_number: 'TF-2026-0142',
    title: 'USDT investment fraud',
    ncrp_reference: null,
    fir_reference: null,
    description: null,
    reported_loss_inr: null,
    incident_date: null,
    status: 'OPEN',
    priority: 'HIGH',
    owner_id: 1,
    created_at: '2026-08-14T09:32:00Z',
    updated_at: '2026-08-14T09:32:00Z',
    closed_at: null,
  },
}

const VALID_TRON = 'TXn8kL2mQpR4vY7wZ3aB6cD9eF1gH5jK2m'

async function renderIntake(routes: StubRoute[] = []) {
  const calls = stubFetch([CASE, ...routes])
  const rendered = renderWithProviders(<AddressIntakePage />, {
    path: '/cases/:caseId/address',
    route: '/cases/c1/address',
  })
  await screen.findByLabelText(/^Address/)
  return { ...rendered, calls }
}

function typeAddress(value: string) {
  fireEvent.change(screen.getByLabelText(/^Address/), { target: { value } })
}

afterEach(() => vi.unstubAllGlobals())

describe('suspect address intake', () => {
  it('names the chain it recognised without a round trip', async () => {
    await renderIntake()
    typeAddress(VALID_TRON)
    expect(screen.getByText(/Looks like a valid TRON address/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add address' })).toBeEnabled()
  })

  it('explains an unsupported chain instead of just rejecting it', async () => {
    await renderIntake()
    typeAddress('bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq')
    expect(
      screen.getByText(
        'This looks like a Bitcoin address. TraceFall currently supports TRON and Ethereum.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add address' })).toBeDisabled()
  })

  it('says how long the address should have been', async () => {
    await renderIntake()
    typeAddress('TXn8kL2mQpR4vY7wZ3aB6cD9eF1gH5jK')
    expect(screen.getByText('A TRON address is 34 characters; this one is 32')).toBeInTheDocument()
  })

  it('surfaces the backend checksum message on the address field', async () => {
    await renderIntake([
      {
        match: 'POST /api/v1/cases/c1/addresses',
        status: 422,
        body: apiError(
          'INVALID_ADDRESS',
          'Checksum does not match — the address may have been mistyped',
          'address',
        ),
      },
    ])
    typeAddress(VALID_TRON)
    fireEvent.click(screen.getByRole('button', { name: 'Add address' }))

    expect(
      await screen.findByText('Checksum does not match — the address may have been mistyped'),
    ).toBeInTheDocument()
  })

  it('sends the victim amount and time, which anchor the trace', async () => {
    const { calls } = await renderIntake([
      {
        match: 'POST /api/v1/cases/c1/addresses',
        status: 201,
        body: {
          id: 8812,
          address: VALID_TRON,
          display_address: VALID_TRON,
          chain: 'TRON',
          is_contract: false,
          role: 'SUSPECT',
          reported_at: '2026-08-14T09:32:00Z',
          added_at: '2026-08-14T10:00:00Z',
          cross_case_matches: [],
        },
      },
    ])
    typeAddress(VALID_TRON)
    fireEvent.change(screen.getByLabelText('Amount victim sent'), { target: { value: '40000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add address' }))

    await screen.findByText('Address added')
    const post = calls.find((call) => call.method === 'POST')
    expect(post?.body).toMatchObject({
      address: VALID_TRON,
      reported_amount: { value: '40000', asset_symbol: 'USDT' },
    })
  })

  it('warns about a cross-case match before any analysis can be started (FR-07)', async () => {
    await renderIntake([
      {
        match: 'POST /api/v1/cases/c1/addresses',
        status: 201,
        body: {
          id: 8812,
          address: VALID_TRON,
          display_address: VALID_TRON,
          chain: 'TRON',
          is_contract: false,
          role: 'SUSPECT',
          reported_at: null,
          added_at: '2026-08-14T10:00:00Z',
          cross_case_matches: [
            { case_id: 'c9', case_number: 'TF-2026-0091', owner_id: 4 },
          ],
        },
      },
    ])
    typeAddress(VALID_TRON)
    fireEvent.click(screen.getByRole('button', { name: 'Add address' }))

    await waitFor(() =>
      expect(screen.getByText('This address already appears in 1 other case')).toBeInTheDocument(),
    )
    expect(screen.getByRole('link', { name: 'TF-2026-0091' })).toBeInTheDocument()
    // The warning is on screen while the analysis is still un-started.
    expect(screen.getByRole('button', { name: 'Start analysis' })).toBeInTheDocument()
  })
})
