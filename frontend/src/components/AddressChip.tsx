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
import { Badge } from './ui'

export interface AddressChipProps {
  address: string
  chain: ChainCode
  /** EIP-55 checksummed form for display; falls back to the canonical value. */
  displayAddress?: string
  tier?: AttributionTier
  confidence?: number | null
  showExplorer?: boolean
  showChain?: boolean
  /** `full` shows the whole address, for a page whose subject it is. */
  size?: 'sm' | 'md' | 'lg' | 'full'
  className?: string
}

/** Copy with a two-second confirmation. Shared by the address and hash chips. */
export function useCopy(value: string) {
  const [copied, setCopied] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => () => clearTimeout(timer.current), [])

  async function copy() {
    try {
      await navigator.clipboard?.writeText(value)
      setCopied(true)
      clearTimeout(timer.current)
      timer.current = setTimeout(() => setCopied(false), 2000)
    } catch {
      // A denied clipboard is not an error worth interrupting the investigator for;
      // the full value is selectable in the title.
    }
  }
  return { copied, copy }
}

const ICON_BUTTON =
  'transition-ui inline-flex h-5 w-5 items-center justify-center rounded text-[var(--muted)] hover:bg-[var(--surface-3)] hover:text-[var(--text)]'

export function AddressChip({
  address,
  chain,
  displayAddress,
  tier,
  confidence,
  showExplorer = true,
  showChain = true,
  size = 'md',
  className = '',
}: AddressChipProps) {
  const full = displayAddress ?? address
  const { copied, copy } = useCopy(full)
  const text = {
    sm: 'text-xs',
    md: 'text-[0.8125rem]',
    lg: 'text-[0.9375rem]',
    full: 'text-[0.9375rem] break-all',
  }[size]

  return (
    <span className={`inline-flex min-w-0 items-center gap-1.5 ${className}`}>
      <code
        title={full}
        className={`font-mono tracking-tight text-[var(--text)] ${text}`}
        data-testid="address-chip-value"
      >
        {size === 'full' ? full : truncateAddress(full)}
      </code>
      <button
        type="button"
        onClick={copy}
        aria-label={`Copy full address ${full}`}
        title="Copy address"
        className={`${ICON_BUTTON} ${copied ? 'text-[var(--success-fg)]' : ''}`}
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
          title="Open on block explorer"
          className={ICON_BUTTON}
        >
          <ExternalLinkIcon />
        </a>
      )}
      {showChain && (
        <Badge tone="info" size="xs">
          {chain}
        </Badge>
      )}
      {tier && <TierBadge tier={tier} confidence={confidence} />}
    </span>
  )
}

/** A transaction hash or digest: mono, middle-truncated, copyable, optional explorer link. */
export function HashChip({
  hash,
  chain,
  label = 'hash',
  head = 8,
  tail = 6,
  className = '',
}: {
  hash: string
  chain?: ChainCode
  label?: string
  head?: number
  tail?: number
  className?: string
}) {
  const { copied, copy } = useCopy(hash)
  return (
    <span className={`inline-flex items-center gap-1 ${className}`}>
      <code title={hash} className="font-mono text-xs tracking-tight text-[var(--text-2)]">
        {truncateAddress(hash, head, tail)}
      </code>
      <button
        type="button"
        onClick={copy}
        aria-label={`Copy ${label} ${hash}`}
        title={`Copy ${label}`}
        className={`${ICON_BUTTON} ${copied ? 'text-[var(--success-fg)]' : ''}`}
      >
        {copied ? <CheckIcon className="h-3 w-3" /> : <CopyIcon className="h-3 w-3" />}
      </button>
      {chain && (
        <a
          href={explorerUrl(chain, hash, 'tx')}
          target="_blank"
          rel="noreferrer noopener"
          aria-label={`Open transaction ${hash} on the ${chain} block explorer (opens in a new tab)`}
          title="Open transaction on block explorer"
          className={ICON_BUTTON}
        >
          <ExternalLinkIcon className="h-3 w-3" />
        </a>
      )}
    </span>
  )
}
