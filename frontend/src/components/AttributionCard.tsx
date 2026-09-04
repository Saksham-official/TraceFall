/**
 * The card that carries the product's central integrity rule.
 *
 * CONFIRMED, PROBABLE, and UNATTRIBUTED are never collapsed and never rendered in a shape
 * where one could be mistaken for another. Each tier gets its own heading sentence, its own
 * border style, and its own icon — so the distinction survives greyscale printing, a bad
 * projector, and a screen reader.
 */

import type { Attribution, AttributionTier, ChainCode } from '../api/types'
import { AddressChip } from './AddressChip'
import { TIER_BORDER, TierBadge } from './TierBadge'

/** One plain-language sentence per tier. This is what makes the tiers textually distinct. */
const TIER_HEADING: Record<AttributionTier, string> = {
  CONFIRMED:
    'Confirmed attribution — this address is matched to a named entity by direct evidence.',
  PROBABLE:
    'Likely attribution — this address behaves like an address of the named entity. It is not confirmed.',
  UNATTRIBUTED: 'Unattributed — no entity claim is made for this address.',
}

const DEFAULT_PROBABLE_DISCLAIMER =
  'Probabilistic attribution. Not confirmation that this address is controlled by the named entity.'

export interface AttributionCardProps {
  attribution: Attribution
  address: string
  chain: ChainCode
  displayAddress?: string
  className?: string
}

export function AttributionCard({
  attribution,
  address,
  chain,
  displayAddress,
  className = '',
}: AttributionCardProps) {
  const { tier } = attribution
  const evidence = attribution.evidence ?? []

  return (
    <article
      data-tier={tier}
      aria-label={`${tier} attribution for ${displayAddress ?? address}`}
      className={`rounded-lg bg-[var(--surface)] p-3 ${TIER_BORDER[tier]} ${
        tier === 'UNATTRIBUTED' ? 'bg-[var(--surface-2)]' : ''
      } ${className}`}
    >
      <header className="flex flex-wrap items-center justify-between gap-2">
        <AddressChip address={address} chain={chain} displayAddress={displayAddress} />
        <TierBadge tier={tier} confidence={attribution.confidence} />
      </header>

      <p className="mt-2 text-[var(--muted)]">{TIER_HEADING[tier]}</p>

      {attribution.tier === 'UNATTRIBUTED' ? (
        <p className="mt-2">{attribution.explanation}</p>
      ) : (
        <>
          <p className="mt-2 text-base font-semibold">
            {attribution.entity.name}
            <span className="ml-2 text-xs font-normal tracking-wide text-[var(--muted)] uppercase">
              {attribution.entity.type}
            </span>
          </p>
          <dl className="mt-1 flex flex-wrap gap-x-4 text-xs text-[var(--muted)]">
            <div>
              <dt className="inline">Method: </dt>
              <dd className="inline">{attribution.method}</dd>
            </div>
            {typeof attribution.confidence === 'number' && (
              <div>
                <dt className="inline">Confidence: </dt>
                <dd className="inline">{attribution.confidence.toFixed(2)}</dd>
              </div>
            )}
          </dl>
        </>
      )}

      {evidence.length > 0 && (
        <section className="mt-3">
          <h4 className="text-xs font-semibold tracking-wide uppercase">Evidence</h4>
          <ul className="mt-1 space-y-1">
            {evidence.map((item) => (
              <li key={item.signal} className="text-[var(--text)]">
                <span className="font-mono text-xs">{item.signal}</span>{' '}
                <span className="font-semibold">{String(item.value)}</span>
                <span className="block text-xs text-[var(--muted)]">{item.detail}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {attribution.tier === 'PROBABLE' && (
        <p className="mt-3 border-t border-dashed border-[var(--border)] pt-2 text-xs text-[var(--muted)]">
          {attribution.disclaimer || DEFAULT_PROBABLE_DISCLAIMER}
        </p>
      )}
    </article>
  )
}
