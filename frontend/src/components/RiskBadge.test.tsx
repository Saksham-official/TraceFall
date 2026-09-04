import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { RiskBadge } from './RiskBadge'
import { RISK_BANDS } from '../api/types'

describe('RiskBadge', () => {
  it('always shows the band word alongside the colour (NFR-18)', () => {
    for (const band of RISK_BANDS) {
      const { container } = render(<RiskBadge score={42} band={band} />)
      expect(container.textContent).toContain(band)
    }
  })

  it('describes score, band, and confidence to assistive technology', () => {
    render(<RiskBadge score={83.6} band="CRITICAL" confidence={0.78} />)
    expect(
      screen.getByRole('img', { name: 'Risk 84 of 100, band CRITICAL, confidence 0.78' }),
    ).toBeInTheDocument()
  })

  it('omits confidence rather than inventing one', () => {
    render(<RiskBadge score={12} band="LOW" />)
    expect(screen.getByRole('img', { name: 'Risk 12 of 100, band LOW' })).toBeInTheDocument()
    expect(screen.queryByText(/conf\./)).not.toBeInTheDocument()
  })
})
