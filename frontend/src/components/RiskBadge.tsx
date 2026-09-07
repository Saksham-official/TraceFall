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
      className={`risk-${band} inline-flex items-baseline rounded-[var(--radius-sm)] border whitespace-nowrap ${
        size === 'lg' ? 'gap-2 px-2.5 py-1' : 'gap-1.5 px-1.5 py-0.5 text-xs'
      } ${className}`}
    >
      <span className={`text-num font-semibold ${size === 'lg' ? 'text-xl leading-6' : ''}`}>
        {rounded}
      </span>
      <span className={`font-semibold tracking-wide uppercase ${size === 'lg' ? 'text-xs' : 'text-[0.6875rem]'}`}>
        {band}
      </span>
      {typeof confidence === 'number' && (
        <span className={`text-num font-normal opacity-75 ${size === 'lg' ? 'text-xs' : 'text-[0.6875rem]'}`}>
          conf. {confidence.toFixed(2)}
        </span>
      )}
    </span>
  )
}
