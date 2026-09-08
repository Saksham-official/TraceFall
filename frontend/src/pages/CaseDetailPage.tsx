import { Link, useParams } from 'react-router-dom'

import {
  useCase,
  useCaseAddresses,
  useCaseAlerts,
  useCaseAnalyses,
  useCaseTimeline,
  ANALYSIS_IS_ACTIVE,
} from '../api/queries'
import type { Alert, Analysis } from '../api/types'
import { canEdit, useAuth } from '../auth'
import { AddressChip } from '../components/AddressChip'
import {
  ActivityIcon,
  ArrowLeftIcon,
  ArrowRightIcon,
  BellIcon,
  ClockIcon,
  GitBranchIcon,
  PlusIcon,
  WalletIcon,
} from '../components/icons'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorNotice,
  Facts,
  Meter,
  Skeleton,
  StatusPill,
} from '../components/ui'
import { formatDate, formatDateTime, formatInr, relativeTime } from '../lib/format'

/**
 * Alerts raised on this case (FR-101). Shown before anything else, because an alert is
 * the system saying an investigator should not have to go looking.
 */
function CaseAlerts({ caseId }: { caseId: string }) {
  const alerts = useCaseAlerts(caseId)
  const items = alerts.data?.items ?? []
  if (items.length === 0) return null
  return (
    <Card padding="none">
      <h2 className="flex items-center gap-2 border-b border-[var(--border)] px-4 py-2.5 text-h3">
        <BellIcon className="h-4 w-4 text-[var(--muted)]" />
        Alerts on this case
        <span className="text-num ml-auto rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-xs font-medium text-[var(--muted)]">
          {items.length}
        </span>
      </h2>
      <ul className="divide-y divide-[var(--border)]">
        {items.map((alert: Alert) => (
          <li key={alert.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-2.5">
            <Badge band={alert.severity} size="xs">
              {alert.severity}
            </Badge>
            <span className="text-secondary min-w-0 flex-1">{alert.trigger_reason}</span>
            <span className="text-meta">
              {alert.acknowledged_at
                ? `acknowledged ${formatDateTime(alert.acknowledged_at)}`
                : 'open'}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  )
}

function RunRow({ run }: { run: Analysis }) {
  const active = ANALYSIS_IS_ACTIVE(run.status)
  const finished = run.status === 'COMPLETED' || run.status === 'PARTIAL'
  return (
    <li>
      <Link
        to={finished ? `/analyses/${run.id}/investigation` : `/analyses/${run.id}`}
        className="transition-ui flex flex-wrap items-center gap-x-3 gap-y-1 rounded-[var(--radius)] border border-[var(--border)] px-3 py-2.5 hover:border-[var(--border-strong)] hover:bg-[var(--surface-2)]"
      >
        <StatusPill status={run.status} />
        <span className="font-mono text-xs text-[var(--muted)]">{run.id.slice(0, 8)}</span>
        {active && (
          <span className="flex min-w-32 items-center gap-2">
            <Meter value={run.progress_pct} band="LOW" className="flex-1" />
            <span className="text-num text-xs text-[var(--muted)]">{run.progress_pct}%</span>
          </span>
        )}
        <span className="text-meta ml-auto">
          {formatDateTime(run.started_at ?? run.completed_at)}
        </span>
        {run.error && (
          <span className="text-secondary w-full text-[var(--danger)]">{run.error}</span>
        )}
        <ArrowRightIcon className="text-[var(--muted)]" />
      </Link>
    </li>
  )
}

function Overview({ caseId }: { caseId: string }) {
  const details = useCase(caseId)
  const addresses = useCaseAddresses(caseId)
  const analyses = useCaseAnalyses(caseId)
  const timeline = useCaseTimeline(caseId)
  // The graph, patterns, attribution, risk and evidence all live in the investigation
  // workspace, against one run. Duplicating them here would mean two answers to the same
  // question, drifting apart.
  const newest = analyses.data?.find((run) => run.status === 'COMPLETED' || run.status === 'PARTIAL')
  const { user } = useAuth()

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="flex min-w-0 flex-col gap-5">
        <Card
          title="Suspect addresses"
          description="The addresses the victim reported. An analysis traces one of them."
          actions={
            canEdit(user) && addresses.data && addresses.data.length > 0 ? (
              <Link to={`/cases/${caseId}/address`}>
                <Button variant="secondary" size="sm" icon={<PlusIcon />}>
                  Add address
                </Button>
              </Link>
            ) : undefined
          }
        >
          {addresses.isPending && <Skeleton lines={2} />}
          {addresses.isError && <ErrorNotice error={addresses.error} />}
          {addresses.data &&
            (addresses.data.length === 0 ? (
              <EmptyState
                title="No addresses on this case"
                icon={<WalletIcon />}
                compact
                action={
                  canEdit(user) ? (
                    <Link to={`/cases/${caseId}/address`}>
                      <Button icon={<PlusIcon />}>Add a suspect address</Button>
                    </Link>
                  ) : undefined
                }
              >
                <p>Add the wallet address the victim sent funds to, with the amount and time.</p>
              </EmptyState>
            ) : (
              <ul className="flex flex-col gap-2">
                {addresses.data.map((entry) => (
                  <li
                    key={entry.id}
                    className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-[var(--radius)] border border-[var(--border)] px-3 py-2"
                  >
                    <AddressChip
                      address={entry.address}
                      displayAddress={entry.display_address}
                      chain={entry.chain}
                      size="lg"
                    />
                    <Badge tone="neutral" size="xs">
                      {entry.role}
                    </Badge>
                    {entry.reported_at && (
                      <span className="text-meta ml-auto">
                        victim sent {formatDateTime(entry.reported_at)}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            ))}
        </Card>

        <Card
          title="Analysis runs"
          description="Each run traces one address with one set of parameters."
          actions={
            newest ? (
              <Link to={`/analyses/${newest.id}/investigation`}>
                <Button size="sm" icon={<GitBranchIcon />}>
                  Open findings
                </Button>
              </Link>
            ) : undefined
          }
        >
          {analyses.isPending && <Skeleton lines={2} />}
          {analyses.isError && <ErrorNotice error={analyses.error} />}
          {analyses.data &&
            (analyses.data.length === 0 ? (
              <EmptyState title="No analysis has been run yet" icon={<GitBranchIcon />} compact>
                <p>Add a suspect address and start an analysis to trace where the funds went.</p>
              </EmptyState>
            ) : (
              <ul className="flex flex-col gap-2">
                {analyses.data.map((run) => (
                  <RunRow key={run.id} run={run} />
                ))}
              </ul>
            ))}
        </Card>
      </div>

      <div className="flex min-w-0 flex-col gap-5">
        <Card title="Case facts">
          {details.data ? (
            <>
              <Facts
                columns={1}
                items={[
                  { label: 'NCRP reference', value: details.data.ncrp_reference ?? '—' },
                  { label: 'FIR reference', value: details.data.fir_reference ?? '—' },
                  { label: 'Reported loss', value: formatInr(details.data.reported_loss_inr) ?? '—' },
                  { label: 'Incident date', value: formatDate(details.data.incident_date) },
                  { label: 'Created', value: formatDateTime(details.data.created_at) },
                  { label: 'Closed', value: formatDateTime(details.data.closed_at) },
                ]}
              />
              {details.data.description && (
                <p className="text-secondary mt-3 border-t border-[var(--border)] pt-3 whitespace-pre-wrap text-[var(--text-2)]">
                  {details.data.description}
                </p>
              )}
            </>
          ) : (
            <Skeleton lines={5} />
          )}
        </Card>

        <Card title="Activity">
          {timeline.isPending && <Skeleton lines={3} />}
          {timeline.isError && <ErrorNotice error={timeline.error} />}
          {timeline.data && timeline.data.length === 0 && (
            <p className="text-secondary text-[var(--muted)]">Nothing has happened on this case yet.</p>
          )}
          {timeline.data && timeline.data.length > 0 && (
            <ol className="relative flex flex-col gap-3 border-l border-[var(--border)] pl-4">
              {timeline.data.map((event) => (
                <li key={event.id} className="relative">
                  <span
                    aria-hidden="true"
                    className="absolute top-1.5 -left-[1.3rem] h-2 w-2 rounded-full border-2 border-[var(--surface)] bg-[var(--border-strong)]"
                  />
                  <p className="font-mono text-xs text-[var(--text-2)]">{event.event_type}</p>
                  <p className="text-meta flex items-center gap-1">
                    <ClockIcon className="h-3 w-3" />
                    <span title={formatDateTime(event.created_at)}>{relativeTime(event.created_at)}</span>
                  </p>
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>
    </div>
  )
}

export function CaseDetailPage() {
  const { caseId = '' } = useParams()
  const { user } = useAuth()
  const details = useCase(caseId)

  if (details.isPending) {
    return (
      <div role="status" aria-label="Loading case" className="flex flex-col gap-5">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-7 w-2/3" />
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
        </div>
      </div>
    )
  }
  if (details.isError)
    return <ErrorNotice error={details.error} onRetry={() => void details.refetch()} />

  const item = details.data

  return (
    <div className="flex flex-col gap-5">
      <div>
        <Link
          to="/"
          className="text-secondary inline-flex items-center gap-1 text-[var(--muted)] hover:text-[var(--text)]"
        >
          <ArrowLeftIcon /> Cases
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="font-mono text-[0.9375rem] font-medium text-[var(--muted)]">
            {item.case_number}
          </span>
          <h1 className="text-h1 min-w-0 flex-1 basis-64">{item.title}</h1>
          <Badge band={item.priority}>{item.priority}</Badge>
          <StatusPill status={item.status} />
          {canEdit(user) && (
            <Link to={`/cases/${caseId}/address`} className="ml-auto">
              <Button variant="secondary" icon={<PlusIcon />}>
                Add address
              </Button>
            </Link>
          )}
        </div>
        <p className="text-meta mt-1 flex items-center gap-1.5">
          <ActivityIcon className="h-3 w-3" />
          Created {relativeTime(item.created_at)} · updated {relativeTime(item.updated_at)}
        </p>
      </div>

      <CaseAlerts caseId={caseId} />
      <Overview caseId={caseId} />
    </div>
  )
}
