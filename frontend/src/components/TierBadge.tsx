/**
 * The single source of truth for how an attribution tier looks.
 *
 * FRONTEND_SPEC §2: each tier has a distinct badge, border style, and icon, and its own
 * words. Colour is never the difference — the label alone tells the tiers apart, which is
 * what makes this readable on a projector, in greyscale, and to a screen reader.
 */

import type { ReactElement } from 'react'

import type { AttributionTier } from '../api/types'
import { DashIcon, QuestionDiamondIcon, ShieldCheckIcon } from './icons'

export const TIER_BORDER: Record<AttributionTier, string> = {
  CONFIRMED: 'border-2 border-solid border-[var(--text)]',
  PROBABLE: 'border-2 border-dashed border-[var(--border-strong)]',
  UNATTRIBUTED: 'border border-[var(--border)]',
}

const TIER_BADGE: Record<AttributionTier, string> = {
  CONFIRMED: 'bg-[var(--text)] text-[var(--bg)] border-2 border-solid border-[var(--text)]',
  PROBABLE: 'bg-[var(--surface)] text-[var(--text)] border-2 border-dashed border-[var(--text-2)]',
  UNATTRIBUTED: 'bg-[var(--surface-2)] text-[var(--muted)] border border-[var(--border-strong)]',
}

const TIER_ICON: Record<AttributionTier, (props: { className?: string }) => ReactElement> = {
  CONFIRMED: ShieldCheckIcon,
  PROBABLE: QuestionDiamondIcon,
  UNATTRIBUTED: DashIcon,
}

/** The words that distinguish the tiers. Never abbreviate one into another's shape. */
export function tierLabel(tier: AttributionTier, confidence?: number | null): string {
  if (tier === 'CONFIRMED') return 'Confirmed'
  if (tier === 'UNATTRIBUTED') return 'Unattributed'
  return typeof confidence === 'number'
    ? `Likely — ${Math.round(confidence * 100)}%`
    : 'Likely'
}

/** The plain-language reading of each tier, for tooltips and rails. */
export const TIER_MEANING: Record<AttributionTier, string> = {
  CONFIRMED: 'Matched to a named, dated public dataset.',
  PROBABLE: 'Behaves like an address of this entity. Verify before acting.',
  UNATTRIBUTED: 'No entity claim is made for this address.',
}

export function TierBadge({
  tier,
  confidence,
  size = 'sm',
}: {
  tier: AttributionTier
  confidence?: number | null
  size?: 'sm' | 'md'
}) {
  const Icon = TIER_ICON[tier]
  return (
    <span
      data-tier={tier}
      title={TIER_MEANING[tier]}
      className={`inline-flex items-center gap-1 rounded-[4px] font-medium whitespace-nowrap ${
        size === 'md' ? 'px-2 py-0.5 text-[0.8125rem]' : 'px-1.5 py-0.5 text-xs'
      } ${TIER_BADGE[tier]}`}
    >
      <Icon />
      {tierLabel(tier, confidence)}
    </span>
  )
}
