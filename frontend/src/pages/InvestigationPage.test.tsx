/**
 * The investigation workspace.
 *
 * These tests are about the product's integrity rules surviving into pixels, not about
 * layout: that a PROBABLE attribution never reads as a fact, that a risk score never
 * appears without its breakdown and confidence, that a pattern never appears without what
 * else produces its shape, and that a truncated graph says so.
 */

import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { InvestigationPage } from './InvestigationPage'
import { expectNoAxeViolations, renderWithProviders, stubFetch } from '../test/utils'

const RUN = 'run-1'
const SUSPECT = 'TMuA6YqfCeX8EhbfYEg5y7S4DqzSJireY9'
const EXCHANGE = 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t'

const ANALYSIS = {
  match: `GET /api/v1/analyses/${RUN}`,
  body: {
    id: RUN,
    case_id: 'case-1',
    root_address_id: 1,
    root_address: SUSPECT,
    status: 'COMPLETED',
    stage: null,
    progress_pct: 100,
    stages: [],
    degradations: [],
    partial_results_available: false,
    started_at: '2026-09-05T10:00:00Z',
    completed_at: '2026-09-05T10:01:00Z',
    error: null,
  },
}

function graph(overrides: Record<string, unknown> = {}) {
  return {
    match: `GET /api/v1/analyses/${RUN}/graph?max_nodes=500`,
    body: {
      root: SUSPECT,
      anchor_tx_hash: null,
      asset_key: 'TRON:USDT',
      node_count: 2,
      edge_count: 1,
      total_nodes: 2,
      truncated: false,
      omitted_node_count: 0,
      nodes: [
        {
          address: SUSPECT,
          depth: 0,
          taint_share: 1,
          tainted_amount_raw: '40000000',
          is_root: true,
          is_terminal: false,
          termination_reason: null,
          attribution_tier: 'PROBABLE',
          entity_name: 'Demo Exchange',
          entity_type: 'EXCHANGE',
          attribution_confidence: 0.8,
          first_reached_at: null,
          omitted_successors: 0,
          pruned_branches: [],
        },
        {
          address: EXCHANGE,
          depth: 1,
          taint_share: 1,
          tainted_amount_raw: '40000000',
          is_root: false,
          is_terminal: true,
          termination_reason: 'SERVICE_BOUNDARY',
          attribution_tier: 'CONFIRMED',
          entity_name: 'Demo Exchange',
          entity_type: 'EXCHANGE',
          attribution_confidence: null,
          first_reached_at: null,
          omitted_successors: 0,
          pruned_branches: [],
        },
      ],
      edges: [
        {
          from: SUSPECT,
          to: EXCHANGE,
          asset_symbol: 'USDT',
          decimals: 6,
          total_amount_raw: '40000000',
          tainted_amount_raw: '40000000',
          transfer_count: 4,
          first_transfer_at: null,
          last_transfer_at: null,
          tx_hashes: ['aa11', 'bb22', 'cc33'],
        },
      ],
      measures: { chokepoints: [], components: 1, cycles: [], highest_value_path: [] },
      pruned_branches: [],
      unavailable_addresses: [],
      ...overrides,
    },
  }
}

const ATTRIBUTIONS = {
  match: `GET /api/v1/analyses/${RUN}/attributions`,
  body: [
    {
      address: EXCHANGE,
      tier: 'CONFIRMED',
      entity_name: 'Demo Exchange',
      entity_type: 'EXCHANGE',
      confidence: null,
      method: 'DATASET_MATCH',
      evidence: [{ type: 'DATASET_MATCH', detail: 'Appears in Demo dataset' }],
      engine_version: '1.0.0',
      computed_at: '2026-09-05T10:01:00Z',
    },
    {
      address: SUSPECT,
      tier: 'PROBABLE',
      entity_name: 'Demo Exchange',
      entity_type: 'EXCHANGE',
      confidence: 0.8,
      method: 'DEPOSIT_HEURISTIC',
      evidence: [{ type: 'SIGNAL', detail: 'Swept 100% of value to one destination' }],
      engine_version: '1.0.0',
      computed_at: '2026-09-05T10:01:00Z',
    },
  ],
}

const PATTERNS = {
  match: `GET /api/v1/analyses/${RUN}/patterns`,
  body: [
    {
      pattern_type: 'FAN_IN',
      severity: 'MEDIUM',
      subject_address: SUSPECT,
      involved_addresses: [],
      trigger_tx_hashes: ['aa11'],
      metrics: { sender_count: 10 },
      explanation: 'Received funds from 10 different addresses.',
      false_positive_note: 'This is the normal shape of an exchange deposit address.',
      detector_version: '1.0.0',
    },
  ],
}

const RISK = {
  match: `GET /api/v1/analyses/${RUN}/risk`,
  body: {
    root: {
      address: SUSPECT,
      score: 23,
      band: 'LOW',
      confidence: 0.88,
      signals: [
        {
          name: 'rapid_transfer',
          weight: 12,
          points: 11.97,
          raw_value: 300,
          description: 'Funds held for a median of 300 seconds before onward transfer.',
          evidence_tx: [],
        },
      ],
      not_evaluated: [
        { name: 'victim_count', reason: 'Backward tracing was not run for this analysis.' },
      ],
      config_version: 'risk-weights-v1.0',
      engine_version: '1.0.0',
      computed_at: '2026-09-05T10:01:00Z',
    },
    nodes: [] as unknown[],
    disclaimer: 'Investigative prioritisation score. Not a probability of fraud.',
  },
}
RISK.body.nodes = [RISK.body.root]

const REPORTS = { match: 'GET /api/v1/cases/case-1/reports', body: [] }

function render(routes = [ANALYSIS, graph(), ATTRIBUTIONS, PATTERNS, RISK, REPORTS]) {
  stubFetch(routes)
  return renderWithProviders(<InvestigationPage />, {
    path: '/analyses/:runId/investigation',
    route: `/analyses/${RUN}/investigation`,
  })
}

afterEach(() => vi.unstubAllGlobals())

describe('investigation workspace', () => {
  it('leads with where the money went and never states a probable finding as fact', async () => {
    render()

    expect(await screen.findByText(/Where the money went/)).toBeInTheDocument()
    // A CONFIRMED attribution exists, so the headline may state it plainly.
    expect(screen.getByText(/confirmed by a named dataset/)).toBeInTheDocument()
  })

  it('states a probable finding as an inference when nothing is confirmed', async () => {
    const probableOnly = {
      ...ATTRIBUTIONS,
      body: ATTRIBUTIONS.body.filter((row) => row.tier === 'PROBABLE'),
    }
    render([ANALYSIS, graph(), probableOnly, PATTERNS, RISK, REPORTS])

    expect(await screen.findByText(/probably/)).toBeInTheDocument()
    expect(
      screen.getByText(/not a confirmed identification, and must be verified/),
    ).toBeInTheDocument()
  })

  it('says so plainly when no service could be identified', async () => {
    render([ANALYSIS, graph(), { ...ATTRIBUTIONS, body: [] }, PATTERNS, RISK, REPORTS])

    expect(await screen.findByText(/No service could be reliably identified/)).toBeInTheDocument()
    expect(screen.getByText(/KYC records held by a VASP/)).toBeInTheDocument()
  })

  it('shows the risk score with its confidence and its breakdown', async () => {
    render()

    // The header and the overview card both carry it — the score is never shown
    // anywhere without its band and its confidence.
    const badges = await screen.findAllByRole('img', { name: /Risk 23 of 100, band LOW/ })
    expect(badges.length).toBeGreaterThanOrEqual(2)
    for (const badge of badges) {
      expect(badge.getAttribute('aria-label')).toContain('confidence 0.88')
    }
    expect(screen.getByText(/Funds held for a median of 300 seconds/)).toBeInTheDocument()
    expect(screen.getByText(/Not a probability of fraud/)).toBeInTheDocument()
  })

  it('keeps not-evaluated signals distinct from zero-scoring ones', async () => {
    render()
    await screen.findByText(/Where the money went/)

    fireEvent.click(screen.getByRole('tab', { name: 'Risk' }))

    expect(await screen.findByText(/not evaluated — not scored as zero/)).toBeInTheDocument()
    expect(screen.getByText(/Backward tracing was not run/)).toBeInTheDocument()
  })

  it('shows every attribution with its tier in words', async () => {
    render()
    await screen.findByText(/Where the money went/)

    fireEvent.click(screen.getByRole('tab', { name: 'Attribution' }))

    expect(await screen.findByText('Confirmed')).toBeInTheDocument()
    // The probable one carries its confidence in the label, never a bare entity name.
    expect(screen.getByText('Likely — 80%')).toBeInTheDocument()
  })

  it('never shows a pattern without what else produces its shape', async () => {
    render()
    await screen.findByText(/Where the money went/)

    fireEvent.click(screen.getByRole('tab', { name: 'Patterns (1)' }))

    expect(await screen.findByText(/Received funds from 10 different addresses/)).toBeInTheDocument()
    expect(screen.getByText(/Also consistent with:/)).toBeInTheDocument()
    expect(
      screen.getByText(/normal shape of an exchange deposit address/),
    ).toBeInTheDocument()
  })

  it('shows a truncated graph as truncated', async () => {
    render([
      ANALYSIS,
      graph({ truncated: true, total_nodes: 120, omitted_node_count: 118, node_count: 2 }),
      ATTRIBUTIONS,
      PATTERNS,
      RISK,
      REPORTS,
    ])
    await screen.findByText(/Where the money went/)

    fireEvent.click(screen.getByRole('tab', { name: 'Graph' }))

    expect(await screen.findByText(/This graph is truncated/)).toBeInTheDocument()
    expect(screen.getByText(/Showing 2 of 120 addresses/)).toBeInTheDocument()
  })

  it('reports a branch that could not be retrieved as a gap, not as an ending', async () => {
    render([
      ANALYSIS,
      graph({ unavailable_addresses: [{ address: EXCHANGE, reason: 'no fixture' }] }),
      ATTRIBUTIONS,
      PATTERNS,
      RISK,
      REPORTS,
    ])
    await screen.findByText(/Where the money went/)

    fireEvent.click(screen.getByRole('tab', { name: 'Graph' }))

    expect(await screen.findByText(/could not be retrieved/)).toBeInTheDocument()
    expect(
      screen.getByText(/not a finding that the funds stopped there/),
    ).toBeInTheDocument()
  })

  it('lists every flow with a route back to its transaction hashes', async () => {
    render()
    await screen.findByText(/Where the money went/)

    fireEvent.click(screen.getByRole('tab', { name: 'Transactions' }))

    expect(await screen.findByText('40000000')).toBeInTheDocument()
    expect(screen.getByText(/aa11, bb22/)).toBeInTheDocument()
  })

  it('offers the graph as a text list as well as a canvas', async () => {
    render()
    await screen.findByText(/Where the money went/)

    fireEvent.click(screen.getByRole('tab', { name: 'Graph' }))

    // The canvas cannot be read by a screen reader, so the same nodes are buttons.
    expect(await screen.findByText('Addresses in this trace')).toBeInTheDocument()
    const nodes = screen.getAllByRole('button', { pressed: false })
    expect(nodes.length).toBeGreaterThanOrEqual(2)
  })

  it('never labels a probable node the same as a confirmed one', async () => {
    // Both carry the same entity name. On the canvas they must still read differently,
    // or the picture collapses the tiers the rest of the product keeps apart.
    render()
    await screen.findByText(/Where the money went/)

    fireEvent.click(screen.getByRole('tab', { name: 'Graph' }))

    const list = await screen.findByText('Addresses in this trace')
    const scope = list.parentElement as HTMLElement
    expect(scope.textContent).toContain('PROBABLE')
    expect(scope.textContent).toContain('CONFIRMED')
  })

  it('has no accessibility violations', async () => {
    const { container } = render()
    await screen.findByText(/Where the money went/)

    await expectNoAxeViolations(container)
  })
})
