/**
 * The investigation workspace — where an investigator reads a finished analysis.
 *
 * Seven tabs over one analysis run. Each renders lazily, so opening the workspace costs one
 * request rather than seven.
 *
 * The integrity rules of the product are the layout rules of this screen:
 * an attribution always shows its tier in words; a risk score always shows its breakdown
 * and its confidence; a pattern always shows what else produces its shape; and anything
 * the analysis could not do is stated on the screen rather than left as a smaller answer.
 */

import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import type {
  Attribution,
  AttributionRow,
  ChainCode,
  GraphEdge,
  GraphPayload,
  PatternRow,
  RiskRow,
} from '../api/types'
import {
  useAnalysis,
  useAttributions,
  useCase,
  useFreezeRequest,
  useGenerateReport,
  useGraph,
  usePatterns,
  useReports,
  useRisk,
} from '../api/queries'
import { AddressChip, HashChip, useCopy } from '../components/AddressChip'
import { AttributionCard } from '../components/AttributionCard'
import { GraphView } from '../components/GraphView'
import { RiskBadge } from '../components/RiskBadge'
import { Tabs } from '../components/Tabs'
import { TierBadge, tierLabel } from '../components/TierBadge'
import {
  ActivityIcon,
  AlertTriangleIcon,
  ArrowLeftIcon,
  BuildingIcon,
  CheckCircleIcon,
  ClockIcon,
  CopyIcon,
  DownloadIcon,
  FileTextIcon,
  GitBranchIcon,
  HashIcon,
  InfoIcon,
  LayersIcon,
  ShieldIcon,
  WalletIcon,
  XCircleIcon,
} from '../components/icons'
import {
  Badge,
  Banner,
  Button,
  Card,
  EmptyState,
  ErrorNotice,
  Meter,
  Skeleton,
  StatTile,
  StatusPill,
} from '../components/ui'
import { download } from '../api/client'
import {
  formatDateTime,
  formatRaw,
  patternLabel,
  relativeTime,
  sharePercent,
  truncateAddress,
} from '../lib/format'

const MAX_NODES = 500
// Ascending, so `indexOf` orders by how much a finding should interrupt the reader.
const SEVERITY_ORDER = ['LOW', 'MEDIUM', 'HIGH'] as const

function chainOf(graph: GraphPayload | undefined): ChainCode {
  return (graph?.asset_key?.split(':')[0] as ChainCode | undefined) ?? 'TRON'
}

export function InvestigationPage() {
  const { runId = '' } = useParams()
  const [selected, setSelected] = useState<string | null>(null)
  const [tab, setTab] = useState('overview')

  const analysis = useAnalysis(runId)
  const graph = useGraph(runId, MAX_NODES)
  const attributions = useAttributions(runId)
  const patterns = usePatterns(runId)
  const risk = useRisk(runId)
  const caseQuery = useCase(analysis.data?.case_id ?? '')

  if (analysis.isPending) {
    return (
      <div role="status" aria-label="Loading analysis" className="flex flex-col gap-5">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-8 w-2/3" />
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
        <Skeleton className="h-10" />
        <Skeleton className="h-64" />
      </div>
    )
  }
  if (analysis.error) return <ErrorNotice error={analysis.error} onRetry={analysis.refetch} />
  if (!analysis.data) return <EmptyState title="Analysis not found" />

  const run = analysis.data
  const chain = chainOf(graph.data)
  const riskByAddress = Object.fromEntries(
    (risk.data?.nodes ?? []).map((row) => [row.address, { score: row.score, band: row.band }]),
  )
  const rootRisk = risk.data?.root ?? null
  const rows = attributions.data ?? []
  const confirmed = rows.filter((a) => a.tier === 'CONFIRMED' && a.entity_name)
  const probable = rows.filter((a) => a.tier === 'PROBABLE' && a.entity_name)

  // Summary numbers from the graph already fetched — nothing is requested twice.
  const nodes = graph.data?.nodes ?? []
  const root = nodes.find((node) => node.is_root)
  const decimals = graph.data?.edges.find((edge) => edge.decimals !== null)?.decimals ?? null
  const symbol = graph.data?.edges.find((edge) => edge.asset_symbol)?.asset_symbol ?? null
  const traced = root ? formatRaw(root.tainted_amount_raw, decimals) : null
  const terminals = nodes.filter((node) => node.is_terminal)
  const services = terminals.filter((node) => node.termination_reason === 'SERVICE_BOUNDARY').length
  const reachedTerminals = root
    ? sharePercent(
        terminals.reduce((sum, node) => sum + BigInt(node.tainted_amount_raw || '0'), 0n).toString(),
        root.tainted_amount_raw,
      )
    : null
  // Distinct named entities of any type — an OFAC party counts as much as an exchange.
  const entities = new Set([...confirmed, ...probable].map((a) => a.entity_name)).size
  const exchanges = new Set(
    [...confirmed, ...probable].filter((a) => a.entity_type === 'EXCHANGE').map((a) => a.entity_name),
  ).size

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <Link
            to={`/cases/${run.case_id}`}
            className="text-secondary inline-flex items-center gap-1 text-[var(--muted)] hover:text-[var(--text)]"
          >
            <ArrowLeftIcon />
            {caseQuery.data ? caseQuery.data.case_number : 'Back to case'}
          </Link>
          {caseQuery.data && (
            <span className="text-secondary truncate text-[var(--muted)]">
              · {caseQuery.data.title}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-label">Investigation workspace</h1>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-2">
              {run.root_address ? (
                <AddressChip address={run.root_address} chain={chain} size="lg" showExplorer />
              ) : (
                <span className="text-h1">Analysis {run.id.slice(0, 8)}</span>
              )}
              <StatusPill status={run.status} />
              {rootRisk && (
                <RiskBadge
                  score={rootRisk.score}
                  band={rootRisk.band}
                  confidence={rootRisk.confidence}
                  size="lg"
                />
              )}
            </div>
            <p className="text-meta mt-1.5 flex flex-wrap items-center gap-x-2">
              <span className="font-mono">run {run.id.slice(0, 8)}</span>
              <span>· started {formatDateTime(run.started_at)}</span>
              {run.completed_at && <span>· finished {formatDateTime(run.completed_at)}</span>}
            </p>
          </div>
          <Button
            variant="secondary"
            icon={<FileTextIcon />}
            onClick={() => setTab('evidence')}
            className="shrink-0"
          >
            Report
          </Button>
        </div>
      </header>

      {run.status === 'PARTIAL' && (
        <Banner tone="warning" title="This analysis is partial" compact>
          {run.degradations.length} stage(s) did not complete. What is missing is listed under
          Evidence — the findings below cover less than the whole picture.
        </Banner>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Risk"
          icon={<ShieldIcon className="h-4 w-4" />}
          value={
            rootRisk ? (
              <span className="flex items-center gap-2">
                {Math.round(rootRisk.score)}
                <Badge band={rootRisk.band}>{rootRisk.band}</Badge>
              </span>
            ) : risk.isPending ? (
              <Skeleton className="h-6 w-16" />
            ) : (
              '—'
            )
          }
          hint={
            rootRisk ? (
              <span className="flex items-center gap-2">
                <Meter value={rootRisk.score} band={rootRisk.band} className="w-24" />
                confidence {rootRisk.confidence.toFixed(2)}
              </span>
            ) : (
              'not scored'
            )
          }
        />
        <StatTile
          label="Traced value"
          icon={<WalletIcon className="h-4 w-4" />}
          value={
            graph.isPending ? (
              <Skeleton className="h-6 w-24" />
            ) : traced ? (
              <span>
                {traced} <span className="text-secondary font-medium text-[var(--muted)]">{symbol}</span>
              </span>
            ) : root ? (
              <span className="font-mono text-base">{root.tainted_amount_raw} raw</span>
            ) : (
              '—'
            )
          }
          hint={
            reachedTerminals !== null
              ? `${reachedTerminals}% reached a trace end point`
              : 'attributed to the suspect address'
          }
        />
        <StatTile
          label="Trace end points"
          icon={<GitBranchIcon className="h-4 w-4" />}
          value={graph.isPending ? <Skeleton className="h-6 w-10" /> : terminals.length}
          hint={
            graph.data
              ? `${services} at a service · ${graph.data.node_count} addresses over ${graph.data.edge_count} flows`
              : ''
          }
        />
        <StatTile
          label="Entities identified"
          icon={<BuildingIcon className="h-4 w-4" />}
          value={attributions.isPending ? <Skeleton className="h-6 w-10" /> : entities}
          tone={confirmed.length > 0 ? 'success' : probable.length > 0 ? 'info' : 'neutral'}
          hint={`${exchanges} exchange${exchanges === 1 ? '' : 's'} · ${confirmed.length} confirmed · ${
            probable.length
          } likely · ${rows.filter((a) => a.tier === 'UNATTRIBUTED').length} unattributed`}
        />
      </div>

      <Tabs
        value={tab}
        onChange={setTab}
        label="Investigation sections"
        tabs={[
          {
            id: 'overview',
            label: 'Overview',
            icon: <InfoIcon />,
            render: () => (
              <Overview
                risk={rootRisk}
                confirmed={confirmed}
                probable={probable}
                patterns={patterns.data ?? []}
                disclaimer={risk.data?.disclaimer}
                run={run}
                graph={graph.data}
              />
            ),
          },
          {
            id: 'graph',
            label: 'Graph',
            icon: <GitBranchIcon />,
            render: () =>
              graph.isPending ? (
                <GraphSkeleton />
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
            icon: <ActivityIcon />,
            render: () =>
              graph.data ? (
                <TransactionTable
                  edges={graph.data.edges}
                  chain={chain}
                  assetKey={graph.data.asset_key}
                  rootAmount={root?.tainted_amount_raw ?? null}
                />
              ) : graph.error ? (
                <ErrorNotice error={graph.error} onRetry={graph.refetch} />
              ) : (
                <Skeleton className="h-48" />
              ),
          },
          {
            id: 'patterns',
            label: `Patterns${patterns.data?.length ? ` (${patterns.data.length})` : ''}`,
            icon: <LayersIcon />,
            render: () =>
              patterns.isPending ? (
                <Skeleton className="h-40" />
              ) : (
                <PatternList patterns={patterns.data ?? []} chain={chain} />
              ),
          },
          {
            id: 'attribution',
            label: 'Attribution',
            icon: <BuildingIcon />,
            render: () =>
              attributions.isPending ? (
                <Skeleton className="h-40" />
              ) : (
                <AttributionList rows={rows} chain={chain} />
              ),
          },
          {
            id: 'risk',
            label: 'Risk',
            icon: <ShieldIcon />,
            render: () =>
              risk.isPending ? (
                <Skeleton className="h-40" />
              ) : (
                <RiskPanel rows={risk.data?.nodes ?? []} disclaimer={risk.data?.disclaimer} />
              ),
          },
          {
            id: 'evidence',
            label: 'Evidence',
            icon: <HashIcon />,
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

function GraphSkeleton() {
  return (
    <div role="status" aria-label="Building graph" className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_19rem]">
      <Skeleton className="h-[420px]" />
      <Skeleton lines={8} />
    </div>
  )
}

const HOUR = 60 * 60 * 1000
const ACT_NOW_WITHIN = 48 * HOUR
const ACT_SOON_WITHIN = 14 * 24 * HOUR

/**
 * When traced value last reached a service we could name, and what that means for acting.
 *
 * The objective is to reach the money while it is still reachable, and nothing on this
 * screen said how old the trail was. Age is the one honest proxy available from public
 * data: we cannot see an exchange's internal ledger, so we cannot know whether the funds
 * are still in the account.
 *
 * So the elapsed time is stated as the fact it is, and the urgency is framed as a general
 * property of exchange balances rather than a claim about these particular funds. Saying
 * "the money is still there" would be exactly the kind of unsupported certainty the tiers
 * exist to prevent.
 */
function lastReachedService(
  graph: GraphPayload | undefined,
  services: AttributionRow[],
): { at: string; ageMs: number } | null {
  const named = new Set(services.map((s) => s.address))
  let newest: { at: string; ageMs: number } | null = null
  for (const edge of graph?.edges ?? []) {
    if (!named.has(edge.to) || !edge.last_transfer_at) continue
    const ageMs = Date.now() - Date.parse(edge.last_transfer_at)
    if (Number.isNaN(ageMs)) continue
    if (newest === null || ageMs < newest.ageMs) {
      newest = { at: edge.last_transfer_at, ageMs }
    }
  }
  return newest
}

function ReachabilityNote({
  graph,
  services,
}: {
  graph: GraphPayload | undefined
  services: AttributionRow[]
}) {
  const reached = lastReachedService(graph, services)
  if (reached === null) return null
  const urgent = reached.ageMs <= ACT_NOW_WITHIN
  const soon = !urgent && reached.ageMs <= ACT_SOON_WITHIN
  return (
    <p
      className={`text-secondary mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-[var(--radius)] border px-3 py-2 ${
        urgent
          ? 'border-[var(--danger-border)] bg-[var(--danger-bg)] text-[var(--danger-fg)]'
          : 'border-[var(--border)] bg-[var(--surface-2)]'
      }`}
    >
      <ClockIcon className="h-3.5 w-3.5 shrink-0" />
      <span>
        Traced value last reached an identified service{' '}
        <strong>{relativeTime(reached.at)}</strong>.
      </span>
      <span className="text-meta">
        {urgent
          ? 'Exchange balances are typically moved within days, so a freeze request is most useful now. Whether the funds remain in the account cannot be seen from public data.'
          : soon
            ? 'Still worth a freeze request, though the balance may already have moved. Public data cannot show whether it has.'
            : 'The trail is old. A KYC request may still identify the account even if the balance has gone.'}
      </span>
    </p>
  )
}

function Overview({
  risk,
  confirmed,
  probable,
  patterns,
  disclaimer,
  run,
  graph,
}: {
  risk: RiskRow | null
  confirmed: AttributionRow[]
  probable: AttributionRow[]
  patterns: PatternRow[]
  disclaimer?: string
  run: { id: string; started_at: string | null; completed_at: string | null; status: string }
  graph?: GraphPayload
}) {
  // Most severe first, so the five shown are the five worth reading.
  const headlinePatterns = [...patterns]
    .sort((a, b) => SEVERITY_ORDER.indexOf(b.severity) - SEVERITY_ORDER.indexOf(a.severity))
    .slice(0, 5)
  const fired = risk ? [...risk.signals].sort((a, b) => b.points - a.points).slice(0, 4) : []

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="flex min-w-0 flex-col gap-4">
        <Card className="border-l-4 border-l-[var(--accent)]">
          <h2 className="text-h2 mb-2 flex items-center gap-2">
            <BuildingIcon className="h-4 w-4 text-[var(--accent)]" />
            Where the money went
          </h2>
          {confirmed.length > 0 ? (
            <p className="leading-6">
              Traced value reached{' '}
              <strong>{[...new Set(confirmed.map((a) => a.entity_name))].join(', ')}</strong>,
              confirmed by a named dataset. A KYC or freeze request naming these addresses may
              identify the receiving account.
            </p>
          ) : probable.length > 0 ? (
            <p className="leading-6">
              Traced value <strong>probably</strong> reached{' '}
              {probable[0].entity_name} ({Math.round((probable[0].confidence ?? 0) * 100)}%
              confidence). This is an inference from transaction behaviour, not a confirmed
              identification, and must be verified before it is acted on.
            </p>
          ) : (
            <p className="leading-6">
              No service could be reliably identified. Identifying the controller requires KYC
              records held by a VASP, or data sources beyond public blockchain analytics.
            </p>
          )}
          <ReachabilityNote graph={graph} services={[...confirmed, ...probable]} />
          {(confirmed.length > 0 || probable.length > 0) && (
            <ul className="mt-3 flex flex-col gap-1.5 border-t border-[var(--border)] pt-3">
              {[...confirmed, ...probable].slice(0, 6).map((row) => (
                <li key={row.address} className="text-secondary flex flex-wrap items-center gap-x-3 gap-y-1">
                  <code className="font-mono text-xs" title={row.address}>
                    {truncateAddress(row.address)}
                  </code>
                  <span className="font-medium">{row.entity_name}</span>
                  <span className="text-meta ml-auto">
                    {row.tier === 'CONFIRMED' ? 'confirmed by dataset' : `likely, ${tierLabel(row.tier, row.confidence).replace('Likely — ', '')} confidence`}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title="Behavioural patterns"
          description={
            patterns.length === 0
              ? 'None detected in this trace.'
              : `${patterns.length} finding${patterns.length === 1 ? '' : 's'}, most severe first.`
          }
        >
          {patterns.length === 0 ? (
            <p className="text-secondary text-[var(--muted)]">
              A trace without patterns is a finding, not a gap — most contain none.
            </p>
          ) : (
            <>
              <ul className="flex flex-col gap-2">
                {headlinePatterns.map((pattern, index) => (
                  <li key={`${pattern.pattern_type}-${index}`} className="flex items-start gap-2.5">
                    <Badge band={pattern.severity} size="xs" className="mt-0.5 w-16 justify-center">
                      {pattern.severity}
                    </Badge>
                    <span className="text-secondary min-w-0">
                      <strong>{patternLabel(pattern.pattern_type)}</strong>
                      <span className="text-[var(--muted)]"> — {pattern.explanation}</span>
                    </span>
                  </li>
                ))}
              </ul>
              {patterns.length > headlinePatterns.length && (
                // A trace through service addresses produces dozens of findings, and an
                // overview that lists all of them is not an overview. The count is shown so
                // nothing looks hidden; the Patterns tab has every one with its
                // false-positive note.
                <p className="text-meta mt-3">
                  {patterns.length - headlinePatterns.length} more finding
                  {patterns.length - headlinePatterns.length === 1 ? '' : 's'}, with their
                  false-positive notes, are in the Patterns tab.
                </p>
              )}
            </>
          )}
        </Card>
      </div>

      <div className="flex min-w-0 flex-col gap-4">
        {risk && (
          <Card title="Why this score" description="The four strongest signals. Every signal is in the Risk tab.">
            <div className="flex items-center gap-3">
              <RiskBadge score={risk.score} band={risk.band} confidence={risk.confidence} size="lg" />
              <Meter value={risk.score} band={risk.band} className="flex-1" />
            </div>
            <ul className="mt-4 flex flex-col gap-2.5">
              {fired.map((signal) => (
                <li key={signal.name}>
                  <div className="flex items-baseline justify-between gap-2 text-xs">
                    <span className="font-mono text-[var(--text-2)]">{signal.name}</span>
                    <span className="text-num text-[var(--muted)]">
                      +{signal.points.toFixed(1)} / {signal.weight}
                    </span>
                  </div>
                  <Meter
                    value={signal.weight > 0 ? (signal.points / signal.weight) * 100 : 0}
                    band={risk.band}
                    className="mt-1"
                  />
                  <p className="text-secondary mt-1 text-[var(--muted)]">{signal.description}</p>
                </li>
              ))}
              {fired.length === 0 && (
                <li className="text-secondary text-[var(--muted)]">No signal fired.</li>
              )}
            </ul>
            {disclaimer && (
              <p className="text-meta mt-3 flex gap-1.5 border-t border-[var(--border)] pt-3">
                <InfoIcon className="mt-0.5 h-3 w-3 shrink-0" />
                {disclaimer}
              </p>
            )}
          </Card>
        )}

        <Card title="Provenance">
          <dl className="text-secondary grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
            <dt className="text-[var(--muted)]">Run</dt>
            <dd className="font-mono text-xs">{run.id}</dd>
            <dt className="text-[var(--muted)]">Started</dt>
            <dd>{formatDateTime(run.started_at)}</dd>
            <dt className="text-[var(--muted)]">Finished</dt>
            <dd>{formatDateTime(run.completed_at)}</dd>
            {graph?.asset_key && (
              <>
                <dt className="text-[var(--muted)]">Asset</dt>
                <dd className="font-mono text-xs break-all">{graph.asset_key}</dd>
              </>
            )}
            {graph?.anchor_tx_hash && (
              <>
                <dt className="text-[var(--muted)]">Anchor</dt>
                <dd>
                  <HashChip hash={graph.anchor_tx_hash} chain={chainOf(graph)} label="anchor transaction" />
                </dd>
              </>
            )}
            <dt className="text-[var(--muted)]">Taint model</dt>
            <dd>proportional (haircut) — a convention, not a measurement</dd>
          </dl>
        </Card>
      </div>
    </div>
  )
}

function TransactionTable({
  edges,
  chain,
  assetKey,
  rootAmount,
}: {
  edges: GraphEdge[]
  chain: ChainCode
  assetKey: string | null
  rootAmount: string | null
}) {
  if (edges.length === 0) {
    return (
      <EmptyState title="No flows in this trace" icon={<ActivityIcon />}>
        The traced value did not leave the suspect address within the analysis window.
      </EmptyState>
    )
  }
  const contract = assetKey?.split(':')[1]
  const th = 'sticky top-0 bg-[var(--surface-2)] px-3 py-2 text-left text-label whitespace-nowrap'
  return (
    <Card padding="none" className="overflow-hidden">
      <div className="max-h-[70vh] overflow-auto">
        <table className="w-full min-w-[56rem] text-sm">
          <caption className="sr-only">Aggregated value flows in this trace</caption>
          <thead>
            <tr>
              <th scope="col" className={th}>From</th>
              <th scope="col" className={th}>To</th>
              <th scope="col" className={th}>Asset</th>
              <th scope="col" className={`${th} text-right`}>Tainted amount</th>
              <th scope="col" className={`${th} text-right`}>Transfers</th>
              <th scope="col" className={th}>When</th>
              <th scope="col" className={th}>Hashes</th>
            </tr>
          </thead>
          <tbody>
            {edges.map((edge) => {
              const amount = formatRaw(edge.tainted_amount_raw, edge.decimals)
              const share = rootAmount ? sharePercent(edge.tainted_amount_raw, rootAmount) : null
              return (
                <tr
                  key={`${edge.from}-${edge.to}`}
                  className="border-t border-[var(--border)] align-top odd:bg-[var(--surface)] even:bg-[var(--surface-2)]/40 hover:bg-[var(--accent-soft)]/40"
                >
                  <td className="px-3 py-2">
                    <AddressChip address={edge.from} chain={chain} size="sm" showChain={false} />
                  </td>
                  <td className="px-3 py-2">
                    <AddressChip address={edge.to} chain={chain} size="sm" showChain={false} />
                  </td>
                  <td className="px-3 py-2">
                    {/* A symbol is never an identity: the contract is on the row (LIMITATIONS §2). */}
                    <span title={contract ? `contract ${contract}` : undefined} className="font-medium">
                      {edge.asset_symbol ?? '—'}
                    </span>
                    {contract && (
                      <span className="text-meta block font-mono">{truncateAddress(contract, 6, 6)}</span>
                    )}
                  </td>
                  <td className="text-num px-3 py-2 text-right">
                    {amount ? (
                      <span className="font-medium">{amount}</span>
                    ) : (
                      <span className="text-meta">decimals unknown</span>
                    )}
                    {share !== null && <span className="text-meta ml-1">({share}%)</span>}
                    {/* Raw units, exact. The displayed amount is derived from this by
                        integer arithmetic; the raw integer stays on the row as evidence. */}
                    <span className="text-meta block font-mono">{edge.tainted_amount_raw}</span>
                  </td>
                  <td className="text-num px-3 py-2 text-right">{edge.transfer_count}</td>
                  <td className="text-meta px-3 py-2 whitespace-nowrap">
                    {edge.first_transfer_at ? (
                      <>
                        <span className="block">{formatDateTime(edge.first_transfer_at)}</span>
                        {edge.last_transfer_at && edge.last_transfer_at !== edge.first_transfer_at && (
                          <span className="block">to {formatDateTime(edge.last_transfer_at)}</span>
                        )}
                      </>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <code className="font-mono text-xs text-[var(--text-2)]" title={edge.tx_hashes.join('\n')}>
                        {edge.tx_hashes
                          .slice(0, 2)
                          .map((hash) => truncateAddress(hash, 6, 4))
                          .join(', ')}
                      </code>
                      {edge.tx_hashes.length > 2 && (
                        <Badge tone="neutral" size="xs" title={edge.tx_hashes.slice(2).join('\n')}>
                          +{edge.tx_hashes.length - 2}
                        </Badge>
                      )}
                      {edge.tx_hashes[0] && (
                        <HashChip hash={edge.tx_hashes[0]} chain={chain} label="first transaction hash" head={0} tail={0} className="[&>code]:hidden" />
                      )}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function PatternList({ patterns, chain }: { patterns: PatternRow[]; chain: ChainCode }) {
  if (patterns.length === 0) {
    return (
      <EmptyState title="No behavioural patterns detected" icon={<LayersIcon />}>
        This is a finding, not a gap — most traces contain none.
      </EmptyState>
    )
  }
  const sorted = [...patterns].sort(
    (a, b) => SEVERITY_ORDER.indexOf(b.severity) - SEVERITY_ORDER.indexOf(a.severity),
  )
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {sorted.map((pattern, index) => (
        <Card key={`${pattern.pattern_type}-${index}`} as="article">
          <div className="flex flex-wrap items-center gap-2">
            <Badge band={pattern.severity}>{pattern.severity}</Badge>
            <h3 className="text-h3">{patternLabel(pattern.pattern_type)}</h3>
            <span className="text-meta ml-auto font-mono">{pattern.pattern_type}</span>
          </div>
          <div className="mt-2">
            <AddressChip address={pattern.subject_address} chain={chain} size="sm" />
          </div>
          <p className="text-secondary mt-2">{pattern.explanation}</p>
          {/* Mandatory, and never collapsed behind a disclosure control: a pattern read
              without its false positives becomes a conclusion. */}
          <p className="text-secondary mt-3 flex gap-2 rounded-[var(--radius)] bg-[var(--surface-2)] p-2.5 text-[var(--text-2)]">
            <InfoIcon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--muted)]" />
            <span>
              <strong>Also consistent with:</strong> {pattern.false_positive_note}
            </span>
          </p>
          {pattern.trigger_tx_hashes.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="text-label">Triggering transactions</span>
              {pattern.trigger_tx_hashes.slice(0, 4).map((hash) => (
                <HashChip key={hash} hash={hash} chain={chain} label="transaction hash" />
              ))}
              {pattern.trigger_tx_hashes.length > 4 && (
                <span className="text-meta">+{pattern.trigger_tx_hashes.length - 4}</span>
              )}
            </div>
          )}
        </Card>
      ))}
    </div>
  )
}

/**
 * The API row, reshaped for the card that carries the tier rule. UI-only: nothing is
 * inferred that the row does not state. A feature object becomes one evidence line per
 * measured field rather than a JSON blob.
 */
function toAttribution(row: AttributionRow): Attribution {
  const evidence = row.evidence.flatMap((item) => {
    const detail = item.detail
    if (detail && typeof detail === 'object') {
      return Object.entries(detail as Record<string, unknown>)
        .filter(([, value]) => value !== null && value !== '' && value !== undefined)
        .map(([signal, value]) => ({
          signal,
          value: typeof value === 'number' || typeof value === 'boolean' ? value : String(value),
          detail: '',
        }))
    }
    return [
      {
        signal: typeof item.type === 'string' ? item.type.toLowerCase() : 'evidence',
        value: '',
        detail: typeof detail === 'string' ? detail : '',
      },
    ]
  })
  const entity = { name: row.entity_name ?? 'Unnamed entity', type: row.entity_type }
  if (row.tier === 'CONFIRMED') {
    return { tier: 'CONFIRMED', entity, confidence: null, method: row.method, evidence }
  }
  if (row.tier === 'PROBABLE') {
    return {
      tier: 'PROBABLE',
      entity,
      confidence: row.confidence ?? 0,
      method: row.method,
      evidence,
      disclaimer: '',
    }
  }
  const explanation =
    evidence.map((item) => item.detail).filter(Boolean).join(' ') ||
    'No dataset match, and too little behaviour to infer an operator.'
  return {
    tier: 'UNATTRIBUTED',
    entity: null,
    confidence: null,
    method: row.method,
    evidence: evidence.filter((item) => item.value !== ''),
    explanation,
  }
}

const TIER_GROUPS = [
  { tier: 'CONFIRMED', title: 'Confirmed by dataset', blurb: 'Matched to a named, dated public dataset.' },
  { tier: 'PROBABLE', title: 'Likely by behaviour', blurb: 'Behaves like an address of the named entity. Verify before acting.' },
  { tier: 'UNATTRIBUTED', title: 'Unattributed addresses', blurb: 'No entity claim is made.' },
] as const

function AttributionList({ rows, chain }: { rows: AttributionRow[]; chain: ChainCode }) {
  if (rows.length === 0) {
    return (
      <EmptyState title="No attributions in this analysis" icon={<BuildingIcon />}>
        No address reached in this trace matched a dataset or showed enough behaviour to classify.
      </EmptyState>
    )
  }
  return (
    <div className="flex flex-col gap-6">
      {TIER_GROUPS.map((group) => {
        const members = rows.filter((row) => row.tier === group.tier)
        if (members.length === 0) return null
        return (
          <section key={group.tier} aria-label={`${group.title} attributions`}>
            <div className="mb-2 flex flex-wrap items-baseline gap-x-3">
              <h3 className="text-h2">
                {group.title}
                <span className="text-num ml-1.5 text-sm font-normal text-[var(--muted)]">{members.length}</span>
              </h3>
              <span className="text-meta">{group.blurb}</span>
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              {members.map((row) => (
                <div key={row.address} className="flex flex-col gap-1">
                  <AttributionCard attribution={toAttribution(row)} address={row.address} chain={chain} />
                  <p className="text-meta px-1">
                    {tierLabel(row.tier, row.confidence)} · method {row.method} · engine {row.engine_version}
                  </p>
                </div>
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}

function RiskPanel({ rows, disclaimer }: { rows: RiskRow[]; disclaimer?: string }) {
  if (rows.length === 0) {
    return (
      <EmptyState title="No risk assessments in this analysis" icon={<ShieldIcon />}>
        The risk stage did not run, or produced no scored addresses.
      </EmptyState>
    )
  }
  const sorted = [...rows].sort((a, b) => b.score - a.score)
  return (
    <div className="flex flex-col gap-3">
      {disclaimer && (
        <Banner tone="info" title="What this score is" compact>
          {disclaimer}
        </Banner>
      )}
      {sorted.map((row) => (
        <Card key={row.address} padding="none">
          <div className="flex flex-wrap items-center gap-3 border-b border-[var(--border)] px-4 py-3">
            <RiskBadge score={row.score} band={row.band} confidence={row.confidence} size="lg" />
            <Meter value={row.score} band={row.band} className="min-w-32 flex-1" />
            <code className="font-mono text-xs" title={row.address}>
              {truncateAddress(row.address)}
            </code>
            <span className="text-meta">config {row.config_version}</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Signal breakdown for {row.address}</caption>
              <thead>
                <tr className="text-label">
                  <th scope="col" className="px-4 py-2 text-left">Signal</th>
                  <th scope="col" className="w-44 px-3 py-2 text-left">Points</th>
                  <th scope="col" className="px-3 py-2 text-left">Why</th>
                </tr>
              </thead>
              <tbody>
                {row.signals.map((signal) => (
                  <tr key={signal.name} className="border-t border-[var(--border)] align-top">
                    <td className="px-4 py-2 font-mono text-xs whitespace-nowrap">{signal.name}</td>
                    <td className="px-3 py-2">
                      <span className="text-num text-xs">
                        {signal.points.toFixed(2)} / {signal.weight}
                      </span>
                      <Meter
                        value={signal.weight > 0 ? (signal.points / signal.weight) * 100 : 0}
                        band={row.band}
                        className="mt-1"
                      />
                    </td>
                    <td className="text-secondary px-3 py-2">{signal.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {row.not_evaluated.length > 0 && (
            <details className="border-t border-[var(--border)] px-4 py-2 text-xs">
              {/* Kept distinct from a zero score: "we did not check" and "we checked and
                  found nothing" are different facts (FR-83). */}
              <summary className="cursor-pointer text-[var(--muted)] hover:text-[var(--text)]">
                {row.not_evaluated.length} signal(s) not evaluated — not scored as zero
              </summary>
              <ul className="mt-2 space-y-1 text-[var(--muted)]">
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

/**
 * The draft KYC and freeze request this analysis supports.
 *
 * The report answers "where did the money go"; this is the letter that acts on it. It is
 * shown as text rather than a download because an investigator edits it before sending —
 * it goes out on their letterhead, under their authority, never ours.
 *
 * The tier is badged next to the recipient and never folded into the name: a PROBABLE
 * identification stays visibly probable right up to the point the letter is sent.
 */
function FreezeRequestPanel({ runId }: { runId: string }) {
  const draft = useFreezeRequest(runId)
  const { copied, copy } = useCopy(draft.data?.text ?? '')

  return (
    <Card
      title="Freeze request"
      description="A draft KYC and account-restriction request for the service that received the funds. Review it, then send it on your own letterhead."
    >
      {draft.isPending && <Skeleton className="h-32" />}
      {draft.isError && <ErrorNotice error={draft.error} onRetry={() => void draft.refetch()} />}
      {draft.data && (
        <>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <span className="text-secondary">
              To: {draft.data.recipient_name ?? 'the operator of the receiving address'}
            </span>
            <TierBadge tier={draft.data.tier} confidence={draft.data.confidence} />
            <Button
              className="ml-auto"
              variant="secondary"
              icon={<CopyIcon />}
              onClick={() => void copy()}
            >
              {copied ? 'Copied' : 'Copy letter'}
            </Button>
          </div>
          <pre className="mt-3 max-h-96 overflow-auto rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface-2)] p-3 text-xs leading-relaxed whitespace-pre-wrap">
            {draft.data.text}
          </pre>
        </>
      )}
    </Card>
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
  const complete = degradations.length === 0 && unavailable.length === 0 && pruned.length === 0

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card
        title="Report"
        description="A PDF for the case file, with every finding, its evidence, the limitations, and a SHA-256 of the document itself."
      >
        <p className="text-secondary text-[var(--muted)]">
          Narrative is templated — no text in it is written by a language model.
        </p>
        <Button
          className="mt-3"
          icon={<FileTextIcon />}
          onClick={() => generate.mutate({ analysis_run_id: runId, format: 'PDF' })}
          loading={generate.isPending}
        >
          {generate.isPending ? 'Generating…' : 'Generate PDF report'}
        </Button>
        {generate.error && (
          <div className="mt-3">
            <ErrorNotice error={generate.error} />
          </div>
        )}
        {reports.data && reports.data.length > 0 && (
          <ul className="mt-4 flex flex-col gap-2 border-t border-[var(--border)] pt-3">
            {reports.data.map((report) => (
              <li
                key={report.id}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-[var(--radius)] border border-[var(--border)] px-3 py-2"
              >
                <button
                  type="button"
                  className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--accent)] hover:underline"
                  data-download-url={report.download_url}
                  onClick={() =>
                    void download(
                      report.download_url.replace('/api/v1', ''),
                      `tracefall-${report.id}.${report.format.toLowerCase()}`,
                    )
                  }
                >
                  <DownloadIcon />
                  {report.format} · {new Date(report.generated_at).toLocaleString()}
                </button>
                <span className="text-meta ml-auto font-mono">
                  sha256 {report.content_sha256.slice(0, 16)}…
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <FreezeRequestPanel runId={runId} />

      <Card
        title="What this analysis could not do"
        description="Every gap is stated here, so a smaller answer is never mistaken for the whole one."
      >
        {complete ? (
          <p className="text-secondary flex items-start gap-2">
            <CheckCircleIcon className="mt-0.5 h-4 w-4 shrink-0 text-[var(--success-fg)]" />
            Every stage completed and every branch above the taint threshold was followed.
          </p>
        ) : (
          <ul className="text-secondary flex flex-col gap-2">
            {unavailable.map((item) => (
              <li key={item.address} className="flex items-start gap-2">
                <XCircleIcon className="mt-0.5 h-4 w-4 shrink-0 text-[var(--danger-fg)]" />
                <span>
                  <code className="font-mono text-xs" title={item.address}>
                    {truncateAddress(item.address)}
                  </code>{' '}
                  — could not be retrieved: {item.reason}
                </span>
              </li>
            ))}
            {pruned.length > 0 && (
              <li className="flex items-start gap-2">
                <AlertTriangleIcon className="mt-0.5 h-4 w-4 shrink-0 text-[var(--warning-fg)]" />
                <span>
                  {pruned.length} branch(es) were not followed, below the taint threshold or past
                  the fan-out cap.
                </span>
              </li>
            )}
            {degradations.length > 0 && (
              <li className="flex items-start gap-2">
                <AlertTriangleIcon className="mt-0.5 h-4 w-4 shrink-0 text-[var(--warning-fg)]" />
                <span>{degradations.length} pipeline stage(s) degraded — see the run record.</span>
              </li>
            )}
          </ul>
        )}
      </Card>
    </div>
  )
}
