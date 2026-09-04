import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AttributionCard } from './AttributionCard'
import type { Attribution } from '../api/types'
import { expectNoAxeViolations } from '../test/utils'

const ADDRESS = 'TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE'

const CONFIRMED: Attribution = {
  tier: 'CONFIRMED',
  entity: { id: 1, name: 'Binance', type: 'EXCHANGE' },
  confidence: null,
  method: 'DATASET_MATCH',
  evidence: [{ signal: 'dataset_match', value: 'binance-hot-2', detail: 'Curated dataset entry' }],
}

const PROBABLE: Attribution = {
  tier: 'PROBABLE',
  entity: { id: 2, name: 'Bybit', type: 'EXCHANGE' },
  confidence: 0.87,
  method: 'DEPOSIT_HEURISTIC',
  evidence: [{ signal: 'sweep_consistency', value: 0.96, detail: '31 of 32 receipts swept' }],
  disclaimer: 'Probabilistic attribution.',
}

const UNATTRIBUTED: Attribution = {
  tier: 'UNATTRIBUTED',
  entity: null,
  confidence: null,
  explanation: 'No dataset match and too few transactions to infer behaviour.',
}

function textOf(container: HTMLElement) {
  return container.textContent ?? ''
}

describe('AttributionCard', () => {
  it('gives each tier its own words, not only its own styling', () => {
    const rendered = [CONFIRMED, PROBABLE, UNATTRIBUTED].map((attribution) => {
      const { container } = render(
        <AttributionCard attribution={attribution} address={ADDRESS} chain="TRON" />,
      )
      return textOf(container)
    })

    expect(new Set(rendered).size).toBe(3)
    expect(rendered[0]).toContain('Confirmed attribution')
    expect(rendered[1]).toContain('Likely attribution')
    expect(rendered[2]).toContain('Unattributed — no entity claim is made')
  })

  it('never presents a PROBABLE claim in the shape of a CONFIRMED one', () => {
    const { container } = render(
      <AttributionCard attribution={PROBABLE} address={ADDRESS} chain="TRON" />,
    )
    expect(textOf(container)).not.toContain('Confirmed')
    expect(screen.getByText('Likely — 87%')).toBeInTheDocument()
    expect(screen.getByText('Probabilistic attribution.')).toBeInTheDocument()
  })

  it('states an UNATTRIBUTED address makes no entity claim and names no entity', () => {
    const { container } = render(
      <AttributionCard attribution={UNATTRIBUTED} address={ADDRESS} chain="TRON" />,
    )
    expect(screen.getByText(UNATTRIBUTED.explanation)).toBeInTheDocument()
    expect(textOf(container)).not.toContain('Binance')
    expect(textOf(container)).not.toContain('Likely')
  })

  it('carries the tier on the element as data, for the graph and the PDF to reuse', () => {
    render(<AttributionCard attribution={CONFIRMED} address={ADDRESS} chain="TRON" />)
    const card = screen.getByRole('article')
    expect(card).toHaveAttribute('data-tier', 'CONFIRMED')
    expect(within(card).getByText('Binance')).toBeInTheDocument()
  })

  it('has no axe violations in any tier', async () => {
    for (const attribution of [CONFIRMED, PROBABLE, UNATTRIBUTED]) {
      const { container } = render(
        <AttributionCard attribution={attribution} address={ADDRESS} chain="TRON" />,
      )
      await expectNoAxeViolations(container)
    }
  })
})
