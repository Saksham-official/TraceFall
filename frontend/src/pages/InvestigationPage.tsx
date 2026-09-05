/**
 * The investigation workspace — where an investigator reads a finished analysis.
 *
 * Six tabs over one analysis run. Each renders lazily, so opening the workspace costs one
 * request rather than six.
 *
 * The integrity rules of the product are the layout rules of this screen:
 * an attribution always shows its tier in words; a risk score always shows its breakdown
 * and its confidence; a pattern always shows what else produces its shape; and anything
 * the analysis could not do is stated on the screen rather than left as a smaller answer.
 */

import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import type { AttributionRow, PatternRow, RiskRow } from '../api/types'
import {
  useAnalysis,
  useAttributions,
  useGenerateReport,
  useGraph,
  usePatterns,
  useReports,
  useRisk,
} from '../api/queries'
import { AddressChip } from '../components/AddressChip'
import { GraphView } from '../components/GraphView'
import { RiskBadge } from '../components/RiskBadge'
import { Tabs } from '../components/Tabs'
import { TierBadge, tierLabel } from '../components/TierBadge'
import { Banner, Button, Card, EmptyState, ErrorNotice, Spinner } from '../components/ui'
import { download } from '../api/client'
import { truncateAddress } from '../lib/format'

const MAX_NODES = 500

export function InvestigationPage() {
  const { runId = '' } = useParams()
  const [selected, setSelected] = useState<string | null>(null)

  const analysis = useAnalysis(runId)
  const graph = useGraph(runId, MAX_NODES)
  const attributions = useAttributions(runId)
  const patterns = usePatterns(runId)
  const risk = useRisk(runId)

  if (analysis.isPending) return <Spinner label="Loading analysis" />
  if (analysis.error) return <ErrorNotice error={analysis.error} onRetry={analysis.refetch} />
  if (!analysis.data) return <EmptyState title="Analysis not found" />

  const run = analysis.data
  const riskByAddress = Object.fromEntries(
    (risk.data?.nodes ?? []).map((row) => [row.address, { score: row.score, band: row.band }]),
  )
  const rootRisk = risk.data?.root ?? null

  return (
    <div className="space-y-4">
      <header className="space-y-2">
        <p className="text-xs text-[var(--muted)]">
          <Link to={`/cases/${run.case_id}`} className="underline">
            Back to case
          </Link>
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold">Investigation workspace</h1>
          {rootRisk && (
            <RiskBadge
              score={rootRisk.score}
              band={rootRisk.band}
              confidence={rootRisk.confidence}
              size="lg"
            />
          )}
        </div>
        {run.root_address && (
          <AddressChip address={run.root_address} chain="TRON" showExplorer />
        )}
      </header>

      {run.status === 'PARTIAL' && (
        <Banner tone="warning" title="This analysis is partial">
          {run.degradations.length} stage(s) did not complete. What is missing is listed under
          Evidence — the findings below cover less than the whole picture.
        </Banner>
      )}

      <Tabs
        tabs={[
          {
            id: 'overview',
            label: 'Overview',
            render: () => (
              <Overview
                risk={rootRisk}
                attributions={attributions.data ?? []}
                patterns={patterns.data ?? []}
                disclaimer={risk.data?.disclaimer}
              />
            ),
          },
          {
            id: 'graph',
            label: 'Graph',
            render: () =>
              graph.isPending ? (
                <Spinner label="Building graph" />
              ) : graph.error ? (
                <ErrorNotice error={graph.error} onRetry={graph.refetch} />
              ) : graph.data ? (
                <GraphView
                  graph={graph.data}
                  riskByAddress={riskByAddress}
                  selected={selected}
                  onSelect={setSelected}
                />
              ) : null,
          },
          {
            id: 'transactions',
            label: 'Transactions',
            render: () =>
              graph.data ? (
                <TransactionTable edges={graph.data.edges} />
              ) : (
                <Spinner label="Loading transactions" />
              ),
          },
          {
            id: 'patterns',
            label: `Patterns${patterns.data?.length ? ` (${patterns.data.length})` : ''}`,
            render: () => <PatternList patterns={patterns.data ?? []} />,
          },
          {
            id: 'attribution',
            label: 'Attribution',
            render: () => <AttributionList rows={attributions.data ?? []} />,
          },
          {
            id: 'risk',
            label: 'Risk',
            render: () => <RiskPanel rows={risk.data?.nodes ?? []} disclaimer={risk.data?.disclaimer} />,
          },
          {
            id: 'evidence',
            label: 'Evidence',
            render: () => (
              <EvidencePanel
                caseId={run.case_id}
                runId={runId}
                degradations={run.degradations}
                unavailable={graph.data?.unavailable_addresses ?? []}
                pruned={graph.data?.pruned_branches ?? []}
              />
            ),
          },
        ]}
      />
    </div>
  )
}

function Overview({
  risk,
  attributions,
  patterns,
  disclaimer,
}: {
  risk: RiskRow | null
  attributions: AttributionRow[]
  patterns: PatternRow[]
  disclaimer?: string
}) {
  const confirmed = attributions.filter((a) => a.tier === 'CONFIRMED' && a.entity_name)
  const probable = attributions.filter((a) => a.tier === 'PROBABLE' && a.entity_name)

  return (
    <div className="space-y-4">
      <Card>
        <h2 className="mb-2 font-semibold">Where the money went</h2>
        {confirmed.length > 0 ? (
          <p>
            Traced value reached{' '}
            <strong>{[...new Set(confirmed.map((a) => a.entity_name))].join(', ')}</strong>,
            confirmed by a named dataset. A KYC or freeze request naming these addresses may
            identify the receiving account.
          </p>
        ) : probable.length > 0 ? (
          <p>
            Traced value <strong>probably</strong> reached{' '}
            {probable[0].entity_name} ({Math.round((probable[0].confidence ?? 0) * 100)}%
            confidence). This is an inference from transaction behaviour, not a confirmed
            identification, and must be verified before it is acted on.
          </p>
        ) : (
          <p>
            No service could be reliably identified. Identifying the controller requires KYC
            records held by a VASP, or data sources beyond public blockchain analytics.
          </p>
        )}
      </Card>

      {risk && (
        <Card>
          <h2 className="mb-2 font-semibold">Risk</h2>
          <RiskBadge score={risk.score} band={risk.band} confidence={risk.confidence} size="lg" />
          <ul className="mt-3 space-y-1 text-sm">
            {risk.signals.slice(0, 4).map((signal) => (
              <li key={signal.name}>
                <span className="font-mono text-xs text-[var(--muted)]">
                  +{signal.points.toFixed(1)}/{signal.weight}
                </span>{' '}
                {signal.description}
              </li>
            ))}
          </ul>
          {disclaimer && <p className="mt-3 text-xs text-[var(--muted)]">{disclaimer}</p>}
        </Card>
      )}

      <Card>
        <h2 className="mb-2 font-semibold">Behavioural patterns</h2>
        {patterns.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">None detected in this trace.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {patterns.map((pattern, index) => (
              <li key={`${pattern.pattern_type}-${index}`}>
                <strong>{pattern.pattern_type}</strong> — {pattern.explanation}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}

function TransactionTable({
  edges,
}: {
  edges: { from: string; to: string; tainted_amount_raw: string; total_amount_raw: string; transfer_count: number; asset_symbol: string | null; tx_hashes: string[] }[]
}) {
  if (edges.length === 0) return <EmptyState title="No flows in this trace" />
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">Aggregated value flows in this trace</caption>
        <thead className="text-left text-xs text-[var(--muted)]">
          <tr>
            <th scope="col" className="py-1 pr-3">From</th>
            <th scope="col" className="py-1 pr-3">To</th>
            <th scope="col" className="py-1 pr-3">Asset</th>
            <th scope="col" className="py-1 pr-3">Tainted (raw)</th>
            <th scope="col" className="py-1 pr-3">Transfers</th>
            <th scope="col" className="py-1">Hashes</th>
          </tr>
        </thead>
        <tbody>
          {edges.map((edge) => (
            <tr key={`${edge.from}-${edge.to}`} className="border-t border-[var(--border)]">
              <td className="py-1.5 pr-3 font-mono text-xs">{truncateAddress(edge.from)}</td>
              <td className="py-1.5 pr-3 font-mono text-xs">{truncateAddress(edge.to)}</td>
              <td className="py-1.5 pr-3">{edge.asset_symbol ?? '—'}</td>
              {/* Raw units, exact. Displaying a token amount without its decimals would
                  be a wrong number, so the raw integer is what is shown. */}
              <td className="py-1.5 pr-3 font-mono text-xs">{edge.tainted_amount_raw}</td>
              <td className="py-1.5 pr-3">{edge.transfer_count}</td>
              <td className="py-1.5 font-mono text-xs break-all">
                {edge.tx_hashes.slice(0, 2).join(', ')}
                {edge.tx_hashes.length > 2 && ` +${edge.tx_hashes.length - 2}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function PatternList({ patterns }: { patterns: PatternRow[] }) {
  if (patterns.length === 0) {
    return (
      <EmptyState title="No behavioural patterns detected">
        This is a finding, not a gap — most traces contain none.
      </EmptyState>
    )
  }
  return (
    <div className="space-y-3">
      {patterns.map((pattern, index) => (
        <Card key={`${pattern.pattern_type}-${index}`}>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold">{pattern.pattern_type}</h3>
            <span className="rounded border border-[var(--border)] px-1.5 py-0.5 text-xs">
              {pattern.severity}
            </span>
            <span className="font-mono text-xs text-[var(--muted)]">
              {truncateAddress(pattern.subject_address)}
            </span>
          </div>
          <p className="mt-2 text-sm">{pattern.explanation}</p>
          {/* Mandatory, and never collapsed behind a disclosure control: a pattern read
              without its false positives becomes a conclusion. */}
          <p className="mt-2 rounded bg-[var(--surface-2)] p-2 text-xs text-[var(--muted)]">
            <strong>Also consistent with:</strong> {pattern.false_positive_note}
          </p>
          {pattern.trigger_tx_hashes.length > 0 && (
            <p className="mt-2 font-mono text-xs break-all text-[var(--muted)]">
              {pattern.trigger_tx_hashes.slice(0, 4).join(', ')}
            </p>
          )}
        </Card>
      ))}
    </div>
  )
}

function AttributionList({ rows }: { rows: AttributionRow[] }) {
  if (rows.length === 0) return <EmptyState title="No attributions in this analysis" />
  return (
    <div className="space-y-3">
      {rows.map((row) => (
        <Card key={row.address}>
          <div className="flex flex-wrap items-center gap-2">
            <TierBadge tier={row.tier} confidence={row.confidence} />
            <span className="font-semibold">{row.entity_name ?? 'No entity identified'}</span>
            <span className="text-xs text-[var(--muted)]">{row.entity_type}</span>
          </div>
          <p className="mt-1 font-mono text-xs">{row.address}</p>
          <p className="mt-1 text-xs text-[var(--muted)]">
            {tierLabel(row.tier, row.confidence)} · method {row.method} · engine{' '}
            {row.engine_version}
          </p>
          <ul className="mt-2 space-y-1 text-sm">
            {row.evidence.map((item, index) => (
              <li key={index} className="text-[var(--muted)]">
                • {typeof item.detail === 'string' ? item.detail : JSON.stringify(item.detail)}
              </li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  )
}

function RiskPanel({ rows, disclaimer }: { rows: RiskRow[]; disclaimer?: string }) {
  if (rows.length === 0) return <EmptyState title="No risk assessments in this analysis" />
  return (
    <div className="space-y-3">
      {disclaimer && <Banner tone="info" title="What this score is">{disclaimer}</Banner>}
      {rows.map((row) => (
        <Card key={row.address}>
          <div className="flex flex-wrap items-center gap-3">
            <RiskBadge score={row.score} band={row.band} confidence={row.confidence} />
            <span className="font-mono text-xs">{truncateAddress(row.address)}</span>
            <span className="text-xs text-[var(--muted)]">config {row.config_version}</span>
          </div>
          <table className="mt-3 w-full text-sm">
            <caption className="sr-only">Signal breakdown for {row.address}</caption>
            <thead className="text-left text-xs text-[var(--muted)]">
              <tr>
                <th scope="col" className="py-1 pr-3">Signal</th>
                <th scope="col" className="py-1 pr-3">Points</th>
                <th scope="col" className="py-1">Why</th>
              </tr>
            </thead>
            <tbody>
              {row.signals.map((signal) => (
                <tr key={signal.name} className="border-t border-[var(--border)]">
                  <td className="py-1 pr-3 font-mono text-xs">{signal.name}</td>
                  <td className="py-1 pr-3 font-mono text-xs">
                    {signal.points.toFixed(2)} / {signal.weight}
                  </td>
                  <td className="py-1">{signal.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {row.not_evaluated.length > 0 && (
            <details className="mt-2 text-xs">
              {/* Kept distinct from a zero score: "we did not check" and "we checked and
                  found nothing" are different facts (FR-83). */}
              <summary className="cursor-pointer text-[var(--muted)]">
                {row.not_evaluated.length} signal(s) not evaluated — not scored as zero
              </summary>
              <ul className="mt-1 space-y-0.5 text-[var(--muted)]">
                {row.not_evaluated.map((item) => (
                  <li key={item.name}>
                    <span className="font-mono">{item.name}</span> — {item.reason}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </Card>
      ))}
    </div>
  )
}

function EvidencePanel({
  caseId,
  runId,
  degradations,
  unavailable,
  pruned,
}: {
  caseId: string
  runId: string
  degradations: unknown[]
  unavailable: { address: string; reason: string }[]
  pruned: { from: string; to: string; reason: string }[]
}) {
  const reports = useReports(caseId)
  const generate = useGenerateReport(caseId)

  return (
    <div className="space-y-4">
      <Card>
        <h3 className="mb-2 font-semibold">Report</h3>
        <p className="mb-3 text-sm text-[var(--muted)]">
          A PDF for the case file, with every finding, its evidence, the limitations, and a
          SHA-256 of the document itself. Narrative is templated — no text in it is written by
          a language model.
        </p>
        <Button
          onClick={() => generate.mutate({ analysis_run_id: runId, format: 'PDF' })}
          disabled={generate.isPending}
        >
          {generate.isPending ? 'Generating…' : 'Generate PDF report'}
        </Button>
        {generate.error && <ErrorNotice error={generate.error} />}
        {reports.data && reports.data.length > 0 && (
          <ul className="mt-3 space-y-1 text-sm">
            {reports.data.map((report) => (
              <li key={report.id} className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  className="underline"
                  data-download-url={report.download_url}
                  onClick={() =>
                    void download(
                      report.download_url.replace('/api/v1', ''),
                      `tracefall-${report.id}.${report.format.toLowerCase()}`,
                    )
                  }
                >
                  {report.format} · {new Date(report.generated_at).toLocaleString()}
                </button>
                <span className="font-mono text-xs text-[var(--muted)]">
                  sha256 {report.content_sha256.slice(0, 16)}…
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <h3 className="mb-2 font-semibold">What this analysis could not do</h3>
        {degradations.length === 0 && unavailable.length === 0 && pruned.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">
            Every stage completed and every branch above the taint threshold was followed.
          </p>
        ) : (
          <ul className="space-y-1 text-sm">
            {unavailable.map((item) => (
              <li key={item.address}>
                <span className="font-mono text-xs">{truncateAddress(item.address)}</span> — could
                not be retrieved: {item.reason}
              </li>
            ))}
            {pruned.length > 0 && (
              <li>
                {pruned.length} branch(es) were not followed, below the taint threshold or past
                the fan-out cap.
              </li>
            )}
            {degradations.length > 0 && (
              <li>{degradations.length} pipeline stage(s) degraded — see the run record.</li>
            )}
          </ul>
        )}
      </Card>
    </div>
  )
}
