import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ApiError } from '../api/client'
import { useAddAddress, useCase, useHealth, useStartAnalysis } from '../api/queries'
import { CHAIN_CODES } from '../api/types'
import type { CaseAddress, ChainCode } from '../api/types'
import { AddressChip } from '../components/AddressChip'
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  CheckCircleIcon,
  ChevronRightIcon,
  GitBranchIcon,
  InfoIcon,
} from '../components/icons'
import {
  Badge,
  Banner,
  Button,
  Card,
  ErrorNotice,
  Field,
  Select,
  Skeleton,
  Steps,
  TextArea,
  TextInput,
  errorMessage,
} from '../components/ui'
import { sniffAddress } from '../lib/addressFormat'

// Must match DEFAULT_* in backend/app/schemas/analysis.py — the demo runs on these,
// and config/demo_addresses.yaml is captured for the same window.
const ADVANCED_DEFAULTS = { max_depth: 5, time_window_days: 180, taint_threshold: 0.01 }
const STEPS = ['Case', 'Suspect address', 'Analysis']

const SHOWCASE_CASES = [
  {
    name: 'Binance Fraud Trail',
    badge: 'TRON • High Risk',
    address: 'T9yD14Nj9j7xAB4dbGeiX9h8unyw8chUDN',
    chain: 'TRON' as ChainCode,
    amount: '100000',
    asset: 'USDT',
    desc: 'Multi-hop fund flow → Binance Deposit Address attribution',
  },
  {
    name: 'Complex Fund Movement',
    badge: 'TRON • High Risk',
    address: 'T9yD14Nj9j7xAB4dbGeiX9h8uo1syi2Ves',
    chain: 'TRON' as ChainCode,
    amount: '250000',
    asset: 'USDT',
    desc: 'Peel chain → Fund splitting → Consolidation → VASP sweep',
  },
]


export function AddressIntakePage() {
  const { caseId = '' } = useParams()
  const navigate = useNavigate()
  const caseQuery = useCase(caseId)
  const health = useHealth()
  const addAddress = useAddAddress(caseId)
  const startAnalysis = useStartAnalysis(caseId)

  const [address, setAddress] = useState('')
  const [chain, setChain] = useState<ChainCode | ''>('')
  const [amount, setAmount] = useState('')
  const [asset, setAsset] = useState('USDT')
  const [sentAt, setSentAt] = useState('')
  const [notes, setNotes] = useState('')
  const [advanced, setAdvanced] = useState(ADVANCED_DEFAULTS)
  const [added, setAdded] = useState<CaseAddress | null>(null)

  const sniff = useMemo(() => sniffAddress(address, chain || null), [address, chain])
  // The backend owns checksum validation; its message is authoritative over the sniff.
  const serverFieldError =
    addAddress.error instanceof ApiError && addAddress.error.field === 'address'
      ? addAddress.error.message
      : null
  const fieldError = serverFieldError ?? (address.trim() ? sniff.error : null)

  function submitAddress(event: FormEvent) {
    event.preventDefault()
    addAddress.mutate(
      {
        address: address.trim(),
        chain: chain || null,
        role: 'SUSPECT',
        reported_amount: amount.trim()
          ? { value: amount.trim(), asset_symbol: asset.trim() }
          : null,
        reported_at: sentAt ? new Date(sentAt).toISOString() : null,
        notes: notes.trim() || null,
      },
      { onSuccess: setAdded },
    )
  }

  function beginAnalysis() {
    if (!added) return
    startAnalysis.mutate(
      {
        address_id: added.id,
        max_depth: advanced.max_depth,
        time_window_days: advanced.time_window_days,
        taint_threshold: advanced.taint_threshold,
      },
      { onSuccess: (accepted) => navigate(`/analyses/${accepted.analysis_run_id}`) },
    )
  }

  if (caseQuery.isPending) {
    return (
      <div role="status" aria-label="Loading case" className="mx-auto flex max-w-2xl flex-col gap-4">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-7 w-2/3" />
        <Skeleton className="h-80" />
      </div>
    )
  }
  if (caseQuery.isError) return <ErrorNotice error={caseQuery.error} />

  const validHint = !fieldError && sniff.ok

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5">
      <div>
        <Link
          to={`/cases/${caseId}`}
          className="text-secondary inline-flex items-center gap-1 text-[var(--muted)] hover:text-[var(--text)]"
        >
          <ArrowLeftIcon /> {caseQuery.data.case_number}
        </Link>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
          <h1 className="text-h1">{added ? 'Start analysis' : 'Suspect address'}</h1>
          <Steps steps={STEPS} current={added ? 2 : 1} />
        </div>
        <p className="text-secondary mt-1 truncate text-[var(--muted)]">{caseQuery.data.title}</p>
      </div>

      {added ? (
        <>
          <Card>
            <div className="flex items-start gap-3">
              <span className="mt-0.5 text-[var(--success-fg)]">
                <CheckCircleIcon className="h-5 w-5" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="font-semibold">Address added</p>
                <div className="mt-2">
                  <AddressChip
                    address={added.address}
                    displayAddress={added.display_address}
                    chain={added.chain}
                    size="lg"
                  />
                </div>
                <p className="text-secondary mt-2 text-[var(--muted)]">
                  The analysis will trace {advanced.max_depth} hops over {advanced.time_window_days}{' '}
                  days, following branches above {(advanced.taint_threshold * 100).toFixed(0)}% of
                  the traced value.
                </p>
              </div>
            </div>
          </Card>

          {/* FR-07: surfaced before analysis starts, not after. */}
          {added.cross_case_matches.length > 0 && (
            <Banner
              tone="warning"
              title={`This address already appears in ${added.cross_case_matches.length} other case${
                added.cross_case_matches.length === 1 ? '' : 's'
              }`}
            >
              <p>Another officer may already be working this address. Coordinate before acting.</p>
              <ul className="mt-2 flex flex-wrap gap-2">
                {added.cross_case_matches.map((match) => (
                  <li key={match.case_id}>
                    <Link
                      to={`/cases/${match.case_id}`}
                      className="font-mono font-medium underline underline-offset-2"
                    >
                      {match.case_number}
                    </Link>
                  </li>
                ))}
              </ul>
            </Banner>
          )}

          {startAnalysis.isError && <ErrorNotice error={startAnalysis.error} />}

          <div className="flex flex-wrap items-center justify-between gap-2">
            <Link to={`/cases/${caseId}`}>
              <Button variant="ghost">Go to case without analysing</Button>
            </Link>
            <Button
              onClick={beginAnalysis}
              loading={startAnalysis.isPending}
              icon={<GitBranchIcon />}
            >
              {startAnalysis.isPending ? 'Starting…' : 'Start analysis'}
            </Button>
          </div>
        </>
      ) : (
        <Card>
          {health.data?.live_mode === false && <div className="mb-5 rounded-[var(--radius)] border border-[var(--accent-soft)] bg-[var(--surface-2)] p-3.5">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-label text-[var(--accent)]">Featured SIH Demo Cases</span>
              <span className="text-meta">Offline Fixture Ready</span>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {SHOWCASE_CASES.map((sc) => (
                <button
                  key={sc.address}
                  type="button"
                  onClick={() => {
                    setAddress(sc.address)
                    setChain(sc.chain)
                    setAmount(sc.amount)
                    setAsset(sc.asset)
                    setNotes(`SIH Demo Case: ${sc.name}. ${sc.desc}`)
                  }}
                  className="flex flex-col items-start rounded border border-[var(--border)] bg-[var(--surface)] p-2.5 text-left transition-colors hover:border-[var(--accent)] hover:bg-[var(--accent-soft)]/20"
                >
                  <div className="flex w-full items-center justify-between font-medium text-[0.8125rem]">
                    <span>{sc.name}</span>
                    <Badge band="HIGH" size="xs">{sc.badge}</Badge>
                  </div>
                  <span className="mt-1 font-mono text-[0.75rem] text-[var(--muted)]">{sc.address}</span>
                  <span className="mt-1 text-[0.75rem] text-[var(--text-2)]">{sc.desc}</span>
                </button>
              ))}
            </div>
          </div>}

          <form onSubmit={submitAddress} className="flex flex-col gap-5" noValidate>

            <Field
              label="Address"
              required
              error={fieldError}
              hint={
                validHint ? (
                  <span className="inline-flex items-center gap-1 text-[var(--success-fg)]">
                    <CheckCircleIcon className="h-3 w-3" />
                    Looks like a valid {sniff.chain} address. The checksum is verified when you add it.
                  </span>
                ) : (
                  'TRON or Ethereum. The chain is detected from the format.'
                )
              }
            >
              {(props) => (
                <TextInput
                  {...props}
                  required
                  autoCapitalize="off"
                  autoCorrect="off"
                  spellCheck={false}
                  className="font-mono"
                  value={address}
                  placeholder="TXn8kL2mQpR4vY7wZ3aB6cD9eF1gH5jK2m"
                  onChange={(e) => setAddress(e.target.value)}
                />
              )}
            </Field>

            <Field label="Chain" hint="Leave on auto-detect unless the format is ambiguous.">
              {(props) => (
                <Select
                  {...props}
                  value={chain}
                  className="sm:w-80"
                  onChange={(e) => setChain(e.target.value as ChainCode | '')}
                >
                  <option value="">
                    Auto-detect{sniff.chain ? ` — detected ${sniff.chain}` : ''}
                  </option>
                  {CHAIN_CODES.map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                </Select>
              )}
            </Field>

            <fieldset className="rounded-[var(--radius)] border border-[var(--accent-soft)] bg-[var(--accent-soft)]/40 p-4">
              <legend className="text-label px-1 text-[var(--accent)]">Anchor the trace</legend>
              <p className="text-secondary mb-3 flex items-start gap-1.5 text-[var(--text-2)]">
                <InfoIcon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--accent)]" />
                These two fields substantially improve the trace — they anchor it to the
                victim&rsquo;s actual transaction.
              </p>
              <div className="grid gap-4 sm:grid-cols-3">
                <Field label="Amount victim sent">
                  {(props) => (
                    <TextInput
                      {...props}
                      inputMode="decimal"
                      className="text-num"
                      value={amount}
                      placeholder="40000"
                      onChange={(e) => setAmount(e.target.value)}
                    />
                  )}
                </Field>
                <Field label="Asset">
                  {(props) => (
                    <TextInput
                      {...props}
                      maxLength={32}
                      className="font-mono"
                      value={asset}
                      onChange={(e) => setAsset(e.target.value)}
                    />
                  )}
                </Field>
                <Field label="Date and time sent">
                  {(props) => (
                    <TextInput
                      {...props}
                      type="datetime-local"
                      value={sentAt}
                      onChange={(e) => setSentAt(e.target.value)}
                    />
                  )}
                </Field>
              </div>
            </fieldset>

            <Field label="Notes">
              {(props) => (
                <TextArea
                  {...props}
                  maxLength={5000}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                />
              )}
            </Field>

            <details className="group rounded-[var(--radius)] border border-[var(--border)]">
              <summary className="flex cursor-pointer items-center gap-2 px-3 py-2.5 text-sm font-medium select-none [&::-webkit-details-marker]:hidden">
                <ChevronRightIcon className="transition-transform group-open:rotate-90" />
                Advanced
                <span className="text-meta font-normal">
                  depth {advanced.max_depth} · window {advanced.time_window_days} days · threshold{' '}
                  {(advanced.taint_threshold * 100).toFixed(0)}%
                </span>
              </summary>
              <div className="grid gap-4 border-t border-[var(--border)] p-3 sm:grid-cols-3">
                <Field label="Max depth" hint="Hops to follow, 1–10.">
                  {(props) => (
                    <TextInput
                      {...props}
                      type="number"
                      min={1}
                      max={10}
                      className="text-num"
                      value={advanced.max_depth}
                      onChange={(e) =>
                        setAdvanced({ ...advanced, max_depth: Number(e.target.value) })
                      }
                    />
                  )}
                </Field>
                <Field label="Time window (days)" hint="Transfers outside it are ignored.">
                  {(props) => (
                    <TextInput
                      {...props}
                      type="number"
                      min={1}
                      max={365}
                      className="text-num"
                      value={advanced.time_window_days}
                      onChange={(e) =>
                        setAdvanced({ ...advanced, time_window_days: Number(e.target.value) })
                      }
                    />
                  )}
                </Field>
                <Field label="Taint threshold" hint="Branches below this share are pruned.">
                  {(props) => (
                    <TextInput
                      {...props}
                      type="number"
                      min={0.001}
                      max={1}
                      step={0.001}
                      className="text-num"
                      value={advanced.taint_threshold}
                      onChange={(e) =>
                        setAdvanced({ ...advanced, taint_threshold: Number(e.target.value) })
                      }
                    />
                  )}
                </Field>
              </div>
            </details>

            {addAddress.isError && !serverFieldError && (
              <Banner tone="error" title={errorMessage(addAddress.error)} compact />
            )}

            <div className="flex items-center justify-between gap-2 border-t border-[var(--border)] pt-4">
              <Link to={`/cases/${caseId}`}>
                <Button type="button" variant="ghost">
                  Skip for now
                </Button>
              </Link>
              <Button
                type="submit"
                loading={addAddress.isPending}
                disabled={!sniff.ok}
                icon={<ArrowRightIcon />}
              >
                {addAddress.isPending ? 'Adding…' : 'Add address'}
              </Button>
            </div>
          </form>
        </Card>
      )}
    </div>
  )
}
