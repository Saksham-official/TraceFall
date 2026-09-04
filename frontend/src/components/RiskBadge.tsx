/**
 * Risk score and band. The band text always accompanies the colour (NFR-18) — this badge
 * has no colour-only mode and must not grow one.
 */

import type { RiskBand } from '../api/types'

export interface RiskBadgeProps {
  score: number
  band: RiskBand
  /** Shown when present; a score without its confidence overstates what we know. */
  confidence?: number | null
  size?: 'sm' | 'lg'
  className?: string
}

export function RiskBadge({ score, band, confidence, size = 'sm', className = '' }: RiskBadgeProps) {
  const rounded = Math.round(score)
  const label =
    `Risk ${rounded} of 100, band ${band}` +
    (typeof confidence === 'number' ? `, confidence ${confidence.toFixed(2)}` : '')

  return (
    <span
      role="img"
      aria-label={label}
      data-band={band}
      className={`risk-${band} inline-flex items-baseline gap-1.5 rounded border px-2 py-0.5 ${
        size === 'lg' ? 'text-base' : 'text-xs'
      } ${className}`}
    >
      <span className={size === 'lg' ? 'text-xl font-semibold' : 'font-semibold'}>{rounded}</span>
      <span className="font-medium tracking-wide uppercase">{band}</span>
      {typeof confidence === 'number' && (
        <span className="opacity-80">conf. {confidence.toFixed(2)}</span>
      )}
    </span>
  )
}
