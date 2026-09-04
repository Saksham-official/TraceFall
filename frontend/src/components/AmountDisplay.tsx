/**
 * An amount, never a bare number (API_SPEC §1).
 *
 * `display` is a string of record. It is shown, not parsed — a float on an amount path
 * silently corrupts large token values. Only the USD approximation, which is already
 * approximate, is formatted numerically.
 */

import type { Amount } from '../api/types'
import { trimTrailingZeros } from '../lib/format'

const USD = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

export interface AmountDisplayProps {
  amount: Amount | null | undefined
  showUsd?: boolean
  className?: string
}

export function AmountDisplay({ amount, showUsd = true, className = '' }: AmountDisplayProps) {
  if (!amount) return <span className={`text-[var(--muted)] ${className}`}>—</span>

  const exact = `${amount.display} ${amount.asset}`
  return (
    <span className={`inline-flex items-baseline gap-1 ${className}`} title={exact}>
      <span className="font-mono tabular-nums">{trimTrailingZeros(amount.display)}</span>
      <span className="text-[var(--muted)]">{amount.asset}</span>
      {showUsd && typeof amount.usd_approx === 'number' && (
        <span className="text-xs text-[var(--muted)]">≈ {USD.format(amount.usd_approx)}</span>
      )}
    </span>
  )
}
