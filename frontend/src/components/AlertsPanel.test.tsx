import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { expectNoAxeViolations, renderWithProviders, stubFetch } from '../test/utils'
import { AlertsPanel } from './AlertsPanel'

const SANCTIONED = {
  id: 7,
  case_id: '11111111-1111-1111-1111-111111111111',
  analysis_run_id: '22222222-2222-2222-2222-222222222222',
  alert_type: 'SANCTIONED_CONTACT',
  severity: 'HIGH',
  address: 'TLFqEhiG7RUSZ9x5iph99Ke5782dkgRnWf',
  trigger_reason: 'TLFqEhiG7RUSZ9x5iph99Ke5782dkgRnWf is on a sanctions list.',
  source_finding_type: 'RISK_ASSESSMENT',
  acknowledged_at: null,
  acknowledged_by: null,
  created_at: new Date().toISOString(),
}

const OPEN_ALERTS = {
  match: 'GET /api/v1/alerts?unacknowledged=true',
  body: { items: [SANCTIONED], next_cursor: null, has_more: false },
}

afterEach(() => vi.unstubAllGlobals())

describe('alerts panel', () => {
  it('states the severity in words, not colour alone', async () => {
    stubFetch([OPEN_ALERTS])
    const { container } = renderWithProviders(<AlertsPanel />)

    expect(await screen.findByText('Sanctioned address in this trace')).toBeInTheDocument()
    expect(screen.getByText('HIGH')).toBeInTheDocument()
    expect(screen.getByText(SANCTIONED.trigger_reason)).toBeInTheDocument()
    await expectNoAxeViolations(container)
  })

  it('keeps the full address available, not only the truncation', async () => {
    stubFetch([OPEN_ALERTS])
    renderWithProviders(<AlertsPanel />)

    const shown = await screen.findByTitle(SANCTIONED.address)
    expect(shown).toBeInTheDocument()
  })

  it('acknowledges an alert and refetches the open list', async () => {
    const calls = stubFetch([
      OPEN_ALERTS,
      { match: 'POST /api/v1/alerts/7/acknowledge', body: { ...SANCTIONED, acknowledged_by: 1 } },
    ])
    renderWithProviders(<AlertsPanel />)

    fireEvent.click(await screen.findByRole('button', { name: /acknowledge/i }))

    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/alerts/7/acknowledge'))).toBe(
        true,
      ),
    )
  })

  it('says nothing is open rather than showing an empty list', async () => {
    stubFetch([
      {
        match: OPEN_ALERTS.match,
        body: { items: [], next_cursor: null, has_more: false },
      },
    ])
    renderWithProviders(<AlertsPanel />)

    expect(await screen.findByText('No open alerts')).toBeInTheDocument()
  })
})
