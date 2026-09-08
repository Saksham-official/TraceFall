/**
 * Cross-case correlation, as an investigator sees it.
 *
 * The integrity rule this guards is that a shared address never reads as a conclusion.
 * It is an on-chain fact; whether two cases are the same fraud is the investigator's call,
 * so the caveat travels with the finding and the panel stays absent when there is nothing
 * to say rather than showing a reassuring empty box.
 */

import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { CaseDetailPage } from './CaseDetailPage'
import { renderWithProviders, stubFetch } from '../test/utils'

const CASE = 'case-1'
const SHARED = 'TLFqEhiG7RUSZ9x5iph99Ke5782dkgRnWf'

const CASE_BODY = {
  match: `GET /api/v1/cases/${CASE}`,
  body: {
    id: CASE,
    case_number: 'TF-2026-0001',
    title: 'Victim one',
    status: 'OPEN',
    priority: 'HIGH',
    ncrp_reference: null,
    fir_reference: null,
    description: null,
    reported_loss_inr: '500000',
    incident_date: null,
    owner_id: 1,
    created_at: '2026-09-05T10:00:00Z',
    updated_at: '2026-09-05T10:00:00Z',
    closed_at: null,
  },
}

const EMPTY_PAGE = { items: [], next_cursor: null, has_more: false }
const NOTE =
  'A shared address is an on-chain fact, not a conclusion that these cases are the same fraud.'

function correlations(shared: unknown[]) {
  return {
    match: `GET /api/v1/cases/${CASE}/correlations`,
    body: { shared_addresses: shared, note: NOTE },
  }
}

function routes(extra: unknown[]) {
  return [
    CASE_BODY,
    { match: `GET /api/v1/cases/${CASE}/alerts`, body: EMPTY_PAGE },
    { match: `GET /api/v1/cases/${CASE}/addresses`, body: [] },
    { match: `GET /api/v1/cases/${CASE}/analyses`, body: [] },
    { match: `GET /api/v1/cases/${CASE}/timeline`, body: [] },
    ...extra,
  ]
}

function render(shared: unknown[]) {
  stubFetch(routes([correlations(shared)]) as never)
  return renderWithProviders(<CaseDetailPage />, {
    path: '/cases/:caseId',
    route: `/cases/${CASE}`,
  })
}

describe('cross-case correlation', () => {
  it('names the other case an address links to', async () => {
    render([
      {
        address: SHARED,
        chain: 'TRON',
        case_count: 1,
        combined_reported_loss_inr: '250000',
        cases: [
          {
            case_id: 'case-2',
            case_number: 'TF-2026-0002',
            title: 'Victim two',
            reported_loss_inr: '250000',
          },
        ],
      },
    ])

    expect(await screen.findByText('Also seen in other cases')).toBeInTheDocument()
    expect(screen.getByText('TF-2026-0002')).toBeInTheDocument()
    expect(screen.getByText('Victim two')).toBeInTheDocument()
    expect(screen.getByText('in 1 other case')).toBeInTheDocument()
  })

  it('never presents a shared address as a conclusion', async () => {
    render([
      {
        address: SHARED,
        chain: 'TRON',
        case_count: 2,
        combined_reported_loss_inr: null,
        cases: [
          { case_id: 'a', case_number: 'TF-2026-0002', title: 'Two', reported_loss_inr: null },
          { case_id: 'b', case_number: 'TF-2026-0003', title: 'Three', reported_loss_inr: null },
        ],
      },
    ])

    expect(await screen.findByText(NOTE)).toBeInTheDocument()
    expect(screen.getByText('in 2 other cases')).toBeInTheDocument()
  })

  it('stays out of the way when nothing correlates', async () => {
    render([])

    expect(await screen.findByText('Victim one')).toBeInTheDocument()
    expect(screen.queryByText('Also seen in other cases')).not.toBeInTheDocument()
  })
})
