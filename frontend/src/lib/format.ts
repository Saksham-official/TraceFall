import type { ChainCode } from '../api/types'

/** Middle-out truncation (FRONTEND_SPEC §2). The full value stays available on hover and copy. */
export function truncateAddress(address: string, head = 6, tail = 7): string {
  if (address.length <= head + tail + 1) return address
  return `${address.slice(0, head)}…${address.slice(-tail)}`
}

const EXPLORERS: Record<ChainCode, { address: string; tx: string }> = {
  TRON: { address: 'https://tronscan.org/#/address/', tx: 'https://tronscan.org/#/transaction/' },
  ETHEREUM: { address: 'https://etherscan.io/address/', tx: 'https://etherscan.io/tx/' },
}

export function explorerUrl(chain: ChainCode, value: string, kind: 'address' | 'tx' = 'address'): string {
  return `${EXPLORERS[chain][kind]}${value}`
}

const INR = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
})

/** Amounts arrive as strings to preserve precision; parse only for display. */
export function formatInr(value: string | number | null | undefined): string | null {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? INR.format(parsed) : String(value)
}

/** Drops trailing zeros for density without altering the value. */
export function trimTrailingZeros(display: string): string {
  return display.includes('.') ? display.replace(/\.?0+$/, '') : display
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString()
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString()
}

export function formatElapsed(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return '—'
  const minutes = Math.round((then - Date.now()) / 60000)
  const scales: [Intl.RelativeTimeFormatUnit, number][] = [
    ['minute', 60],
    ['hour', 24],
    ['day', 30],
  ]
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  let value = minutes
  for (const [unit, limit] of scales) {
    if (Math.abs(value) < limit) return formatter.format(value, unit)
    value = Math.round(value / limit)
  }
  return formatter.format(value, 'month')
}

/**
 * A raw integer amount rendered at its asset's precision, by string arithmetic only.
 *
 * Returns null when decimals are unknown: showing a 6-decimal token as if it had 18
 * would understate it by a factor of a trillion, so the caller must then show the raw
 * value labelled as raw. No float is ever involved (CLAUDE.md §6).
 */
export function formatRaw(raw: string, decimals: number | null | undefined): string | null {
  if (decimals === null || decimals === undefined || !/^-?\d+$/.test(raw)) return null
  const negative = raw.startsWith('-')
  const digits = negative ? raw.slice(1) : raw
  const padded = digits.padStart(decimals + 1, '0')
  const whole = padded.slice(0, padded.length - decimals) || '0'
  const fraction = decimals === 0 ? '' : padded.slice(-decimals).replace(/0+$/, '')
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${negative ? '-' : ''}${grouped}${fraction ? `.${fraction}` : ''}`
}

/** Integer share of `part` in `whole`, as a percentage 0–100, without floats on the amount path. */
export function sharePercent(part: string, whole: string): number | null {
  if (!/^\d+$/.test(part) || !/^\d+$/.test(whole)) return null
  const denominator = BigInt(whole)
  if (denominator === 0n) return null
  return Number((BigInt(part) * 100n) / denominator)
}

/** The plain-language reading of a trace termination reason (ADR-019). */
export const TERMINATION_LABEL: Record<string, string> = {
  MAX_DEPTH: 'Depth limit reached',
  BELOW_THRESHOLD: 'Below the taint threshold',
  SERVICE_BOUNDARY: 'Reached a service — tracing stops here',
  NO_OUTFLOW: 'Funds have not moved on',
  EDGE_BUDGET: 'Edge budget exhausted',
  TIME_WINDOW: 'Outside the time window',
  DATA_UNAVAILABLE: 'Could not be retrieved',
}

export function terminationLabel(reason: string | null | undefined): string | null {
  if (!reason) return null
  return TERMINATION_LABEL[reason] ?? reason.replace(/_/g, ' ').toLowerCase()
}

/** Pattern enums as an investigator reads them. */
export const PATTERN_LABEL: Record<string, string> = {
  FAN_OUT: 'Funds split across many addresses',
  FAN_IN: 'Funds gathered from many addresses',
  RAPID_TRANSFER: 'Funds moved on within minutes',
  PEEL_CHAIN: 'Peel chain — repeated splitting while moving forward',
  STRUCTURING: 'Repeated near-identical amounts',
  DORMANCY_BURST: 'Long dormancy followed by a burst of activity',
  CHAIN_HOPPING: 'Value reached a cross-chain bridge',
}

export function patternLabel(type: string): string {
  return PATTERN_LABEL[type] ?? type.replace(/_/g, ' ').toLowerCase()
}
