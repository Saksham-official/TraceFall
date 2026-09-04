/**
 * Live, client-side address *format* feedback.
 *
 * This mirrors the cheap checks in `backend/app/chains/` — prefix, length, alphabet, and the
 * unsupported-chain hints — so the investigator learns about a mistyped address while typing
 * rather than after a round trip.
 *
 * It deliberately does NOT reimplement the checksums. TRON base58check and the EIP-55
 * checksum stay in exactly one place, the backend, which returns the specific message
 * ("Checksum does not match — the address may have been mistyped") on submit. Two
 * implementations of a security check drift; one of them is then wrong.
 */

import type { ChainCode } from '../api/types'

const BASE58 = /^[1-9A-HJ-NP-Za-km-z]+$/
const HEX40 = /^0x[0-9a-fA-F]{40}$/

export interface AddressSniff {
  chain: ChainCode | null
  /** A definite format failure, in the backend's words. */
  error: string | null
  /** Format is plausible; the checksum is verified server-side on submit. */
  ok: boolean
}

const EMPTY: AddressSniff = { chain: null, error: null, ok: false }

function looksLikeTron(value: string): boolean {
  return value.startsWith('T') && value.length >= 30 && value.length <= 40
}

function looksLikeEthereum(value: string): boolean {
  return value.toLowerCase().startsWith('0x') && value.length >= 30 && value.length <= 50
}

function unsupportedHint(value: string): string | null {
  if (/^(bc1|1|3)/.test(value) && value.length >= 26 && value.length <= 62) return 'Bitcoin'
  if (value.length >= 32 && value.length <= 44 && /^[a-zA-Z0-9]+$/.test(value) && !/^0x/i.test(value))
    return 'Solana'
  return null
}

export function sniffAddress(input: string, forcedChain?: ChainCode | null): AddressSniff {
  const address = input.trim()
  if (!address) return EMPTY

  const chain =
    forcedChain ?? (looksLikeTron(address) ? 'TRON' : looksLikeEthereum(address) ? 'ETHEREUM' : null)

  if (chain === null) {
    const hint = unsupportedHint(address)
    return {
      chain: null,
      error: hint
        ? `This looks like a ${hint} address. TraceFall currently supports TRON and Ethereum.`
        : 'Address format not recognised. TraceFall currently supports TRON and Ethereum.',
      ok: false,
    }
  }

  if (chain === 'TRON') {
    if (!address.startsWith('T')) return { chain, error: "A TRON address starts with 'T'", ok: false }
    if (address.length !== 34)
      return {
        chain,
        error: `A TRON address is 34 characters; this one is ${address.length}`,
        ok: false,
      }
    if (!BASE58.test(address))
      return { chain, error: 'Address contains characters that are not valid base58', ok: false }
    return { chain, error: null, ok: true }
  }

  if (!address.toLowerCase().startsWith('0x'))
    return { chain, error: "An Ethereum address starts with '0x'", ok: false }
  if (address.length !== 42)
    return {
      chain,
      error: `An Ethereum address is 42 characters; this one is ${address.length}`,
      ok: false,
    }
  if (!HEX40.test(address))
    return { chain, error: 'Address contains non-hexadecimal characters', ok: false }
  return { chain, error: null, ok: true }
}
