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
