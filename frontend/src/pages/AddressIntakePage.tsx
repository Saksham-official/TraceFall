import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ApiError } from '../api/client'
import { useAddAddress, useCase, useStartAnalysis } from '../api/queries'
import { CHAIN_CODES } from '../api/types'
import type { CaseAddress, ChainCode } from '../api/types'
import { AddressChip } from '../components/AddressChip'
import {
  Banner,
  Button,
  Card,
  ErrorNotice,
  Field,
  Select,
  Spinner,
  TextArea,
  TextInput,
  errorMessage,
} from '../components/ui'
import { sniffAddress } from '../lib/addressFormat'

const ADVANCED_DEFAULTS = { max_depth: 5, time_window_days: 90, taint_threshold: 0.01 }

export function AddressIntakePage() {
  const { caseId = '' } = useParams()
  const navigate = useNavigate()
  const caseQuery = useCase(caseId)
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

  if (caseQuery.isPending) return <Spinner label="Loading case…" />
  if (caseQuery.isError) return <ErrorNotice error={caseQuery.error} />

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div>
        <p className="text-xs tracking-wide text-[var(--muted)] uppercase">
          Step 2 of 2 — suspect address
        </p>
        <h1 className="text-lg font-semibold">
          {caseQuery.data.case_number} · {caseQuery.data.title}
        </h1>
      </div>

      {added ? (
        <>
          <Card className="flex flex-col gap-2">
            <p className="font-semibold">Address added</p>
            <AddressChip
              address={added.address}
              displayAddress={added.display_address}
              chain={added.chain}
            />
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
                    <Link to={`/cases/${match.case_id}`} className="font-mono underline">
                      {match.case_number}
                    </Link>
                  </li>
                ))}
              </ul>
            </Banner>
          )}

          {startAnalysis.isError && <ErrorNotice error={startAnalysis.error} />}

          <div className="flex gap-2">
            <Button onClick={beginAnalysis} disabled={startAnalysis.isPending}>
              {startAnalysis.isPending ? 'Starting…' : 'Start analysis'}
            </Button>
            <Link to={`/cases/${caseId}`}>
              <Button variant="secondary">Go to case without analysing</Button>
            </Link>
          </div>
        </>
      ) : (
        <Card>
          <form onSubmit={submitAddress} className="flex flex-col gap-3" noValidate>
            <Field
              label="Address"
              required
              error={fieldError}
              hint={
                !fieldError && sniff.ok
                  ? `Looks like a valid ${sniff.chain} address. The checksum is verified when you add it.`
                  : 'TRON or Ethereum. The chain is detected from the format.'
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

            <p className="text-[var(--muted)]">
              These two fields substantially improve the trace — they anchor it to the victim&rsquo;s
              actual transaction.
            </p>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Amount victim sent">
                {(props) => (
                  <TextInput
                    {...props}
                    inputMode="decimal"
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

            <details className="rounded border border-[var(--border)] p-2">
              <summary className="cursor-pointer font-medium">
                Advanced — depth {advanced.max_depth}, window {advanced.time_window_days} days,
                threshold {(advanced.taint_threshold * 100).toFixed(0)}%
              </summary>
              <div className="mt-3 grid gap-3 sm:grid-cols-3">
                <Field label="Max depth">
                  {(props) => (
                    <TextInput
                      {...props}
                      type="number"
                      min={1}
                      max={10}
                      value={advanced.max_depth}
                      onChange={(e) =>
                        setAdvanced({ ...advanced, max_depth: Number(e.target.value) })
                      }
                    />
                  )}
                </Field>
                <Field label="Time window (days)">
                  {(props) => (
                    <TextInput
                      {...props}
                      type="number"
                      min={1}
                      max={365}
                      value={advanced.time_window_days}
                      onChange={(e) =>
                        setAdvanced({ ...advanced, time_window_days: Number(e.target.value) })
                      }
                    />
                  )}
                </Field>
                <Field label="Taint threshold">
                  {(props) => (
                    <TextInput
                      {...props}
                      type="number"
                      min={0.001}
                      max={1}
                      step={0.001}
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
              <Banner tone="error" title={errorMessage(addAddress.error)} />
            )}

            <div className="flex items-center gap-2">
              <Button type="submit" disabled={addAddress.isPending || !sniff.ok}>
                {addAddress.isPending ? 'Adding…' : 'Add address'}
              </Button>
              <Link to={`/cases/${caseId}`}>
                <Button type="button" variant="ghost">
                  Skip for now
                </Button>
              </Link>
            </div>
          </form>
        </Card>
      )}
    </div>
  )
}
