/**
 * An address, never shown as a bare truncated string.
 *
 * Carries the full value on hover and on copy, a link out to a public explorer so the
 * investigator can check our work, and — when known — the attribution tier.
 */

import { useEffect, useRef, useState } from 'react'

import type { AttributionTier, ChainCode } from '../api/types'
import { explorerUrl, truncateAddress } from '../lib/format'
import { TierBadge } from './TierBadge'
import { CheckIcon, CopyIcon, ExternalLinkIcon } from './icons'

export interface AddressChipProps {
  address: string
  chain: ChainCode
  /** EIP-55 checksummed form for display; falls back to the canonical value. */
  displayAddress?: string
  tier?: AttributionTier
  confidence?: number | null
  showExplorer?: boolean
  className?: string
}

export function AddressChip({
  address,
  chain,
  displayAddress,
  tier,
  confidence,
  showExplorer = true,
  className = '',
}: AddressChipProps) {
  const full = displayAddress ?? address
  const [copied, setCopied] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => () => clearTimeout(timer.current), [])

  async function copy() {
    try {
      await navigator.clipboard?.writeText(full)
      setCopied(true)
      clearTimeout(timer.current)
      timer.current = setTimeout(() => setCopied(false), 2000)
    } catch {
      // A denied clipboard is not an error worth interrupting the investigator for;
      // the full address is selectable in the title and in the explorer link.
    }
  }

  return (
    <span className={`inline-flex items-center gap-1.5 ${className}`}>
      <code
        title={full}
        className="font-mono text-[0.8125rem] tracking-tight text-[var(--text)]"
        data-testid="address-chip-value"
      >
        {truncateAddress(full)}
      </code>
      <button
        type="button"
        onClick={copy}
        aria-label={`Copy full address ${full}`}
        className="rounded p-0.5 text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
      >
        {copied ? <CheckIcon /> : <CopyIcon />}
      </button>
      <span aria-live="polite" className="sr-only">
        {copied ? 'Address copied to clipboard' : ''}
      </span>
      {showExplorer && (
        <a
          href={explorerUrl(chain, address)}
          target="_blank"
          rel="noreferrer noopener"
          aria-label={`Open ${full} on the ${chain} block explorer (opens in a new tab)`}
          className="rounded p-0.5 text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
        >
          <ExternalLinkIcon />
        </a>
      )}
      <span className="text-[0.6875rem] font-medium tracking-wide text-[var(--muted)] uppercase">
        {chain}
      </span>
      {tier && <TierBadge tier={tier} confidence={confidence} />}
    </span>
  )
}
