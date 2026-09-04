import { render, screen } from '@testing-library/react'
import { fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { AddressChip } from './AddressChip'
import { expectNoAxeViolations } from '../test/utils'

const TRON = 'TXn8kL2mQpR4vY7wZ3aB6cD9eF1gH5jK2m'
const ETH = '0x742d35cc6634c0532925a3b844bc454e4438f44e'

describe('AddressChip', () => {
  it('truncates middle-out but keeps the full value reachable', () => {
    render(<AddressChip address={TRON} chain="TRON" />)
    const value = screen.getByTestId('address-chip-value')
    expect(value).toHaveTextContent('TXn8kL…gH5jK2m')
    expect(value).toHaveAttribute('title', TRON)
  })

  it('copies the full address, never the truncated one', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } })

    render(<AddressChip address={TRON} chain="TRON" />)
    fireEvent.click(screen.getByRole('button', { name: `Copy full address ${TRON}` }))

    expect(writeText).toHaveBeenCalledWith(TRON)
    expect(await screen.findByText('Address copied to clipboard')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('prefers the checksummed display form for display and copy', () => {
    const display = '0x742d35Cc6634C0532925a3b844Bc454e4438f44e'
    render(<AddressChip address={ETH} chain="ETHEREUM" displayAddress={display} />)
    expect(screen.getByTestId('address-chip-value')).toHaveAttribute('title', display)
    expect(screen.getByRole('button', { name: `Copy full address ${display}` })).toBeInTheDocument()
  })

  it('links to the chain explorer using the canonical address', () => {
    render(<AddressChip address={ETH} chain="ETHEREUM" />)
    expect(screen.getByRole('link')).toHaveAttribute('href', `https://etherscan.io/address/${ETH}`)
  })

  it('shows the attribution tier in words when one is known', () => {
    render(<AddressChip address={TRON} chain="TRON" tier="PROBABLE" confidence={0.87} />)
    expect(screen.getByText('Likely — 87%')).toBeInTheDocument()
  })

  it('has no axe violations', async () => {
    const { container } = render(<AddressChip address={TRON} chain="TRON" tier="CONFIRMED" />)
    await expectNoAxeViolations(container)
  })
})
