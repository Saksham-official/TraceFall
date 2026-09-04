import { Link, useParams } from 'react-router-dom'

import {
  useCase,
  useCaseAddresses,
  useCaseAnalyses,
  useCaseTimeline,
  ANALYSIS_IS_ACTIVE,
} from '../api/queries'
import { canEdit, useAuth } from '../auth'
import { AddressChip } from '../components/AddressChip'
import { Tabs } from '../components/Tabs'
import { Button, Card, EmptyState, ErrorNotice, LaterPhase, Spinner } from '../components/ui'
import { formatDate, formatDateTime, formatInr } from '../lib/format'

/** The four header cards of FRONTEND_SPEC §4, honest about what is not computed yet. */
function HeaderCards() {
  const cards = [
    { title: 'Risk', phase: 'Phase 7' },
    { title: 'Traced', phase: 'Phase 4' },
    { title: 'Terminals', phase: 'Phase 4' },
    { title: 'Exchanges', phase: 'Phase 6' },
  ]
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {cards.map((card) => (
        <div
          key={card.title}
          className="rounded border border-dashed border-[var(--border)] p-3"
        >
          <p className="text-xs font-medium tracking-wide text-[var(--muted)] uppercase">
            {card.title}
          </p>
          <p className="text-xl font-semibold text-[var(--muted)]">—</p>
          <p className="text-xs text-[var(--muted)]">not computed until {card.phase}</p>
        </div>
      ))}
    </div>
  )
}

function Overview({ caseId }: { caseId: string }) {
  const details = useCase(caseId)
  const addresses = useCaseAddresses(caseId)
  const analyses = useCaseAnalyses(caseId)
  const timeline = useCaseTimeline(caseId)

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <h2 className="font-semibold">Case</h2>
        {details.data && (
          <dl className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-2">
            {[
              ['NCRP reference', details.data.ncrp_reference ?? '—'],
              ['FIR reference', details.data.fir_reference ?? '—'],
              ['Reported loss', formatInr(details.data.reported_loss_inr) ?? '—'],
              ['Incident date', formatDate(details.data.incident_date)],
              ['Created', formatDateTime(details.data.created_at)],
              ['Closed', formatDateTime(details.data.closed_at)],
            ].map(([label, value]) => (
              <div key={label} className="flex gap-2">
                <dt className="text-[var(--muted)]">{label}</dt>
                <dd className="ml-auto">{value}</dd>
              </div>
            ))}
          </dl>
        )}
        {details.data?.description && (
          <p className="mt-3 whitespace-pre-wrap">{details.data.description}</p>
        )}
      </Card>

      <Card>
        <h2 className="font-semibold">Suspect addresses</h2>
        {addresses.isPending && <Spinner label="Loading addresses…" />}
        {addresses.isError && <ErrorNotice error={addresses.error} />}
        {addresses.data &&
          (addresses.data.length === 0 ? (
            <div className="mt-3">
              <EmptyState
                title="No addresses on this case"
                action={
                  <Link to={`/cases/${caseId}/address`}>
                    <Button>Add a suspect address</Button>
                  </Link>
                }
              />
            </div>
          ) : (
            <ul className="mt-2 flex flex-col gap-2">
              {addresses.data.map((entry) => (
                <li key={entry.id} className="flex flex-wrap items-center gap-3">
                  <AddressChip
                    address={entry.address}
                    displayAddress={entry.display_address}
                    chain={entry.chain}
                  />
                  <span className="text-xs tracking-wide text-[var(--muted)] uppercase">
                    {entry.role}
                  </span>
                  {entry.reported_at && (
                    <span className="text-xs text-[var(--muted)]">
                      victim sent {formatDateTime(entry.reported_at)}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          ))}
      </Card>

      <Card>
        <h2 className="font-semibold">Analysis runs</h2>
        {analyses.isPending && <Spinner label="Loading runs…" />}
        {analyses.isError && <ErrorNotice error={analyses.error} />}
        {analyses.data &&
          (analyses.data.length === 0 ? (
            <p className="mt-2 text-[var(--muted)]">
              No analysis has been run on this case yet.
            </p>
          ) : (
            <ul className="mt-2 flex flex-col gap-1">
              {analyses.data.map((run) => (
                <li key={run.id}>
                  <Link to={`/analyses/${run.id}`} className="flex flex-wrap items-baseline gap-3">
                    <span className="font-mono text-xs">{run.id.slice(0, 8)}</span>
                    <span className="text-xs font-medium tracking-wide uppercase">
                      {run.status}
                    </span>
                    {ANALYSIS_IS_ACTIVE(run.status) && (
                      <span className="text-xs text-[var(--muted)]">{run.progress_pct}%</span>
                    )}
                    <span className="text-xs text-[var(--muted)]">
                      {formatDateTime(run.started_at ?? run.completed_at)}
                    </span>
                    {run.error && <span className="text-xs text-[var(--danger)]">{run.error}</span>}
                  </Link>
                </li>
              ))}
            </ul>
          ))}
      </Card>

      <Card>
        <h2 className="font-semibold">Activity</h2>
        {timeline.isError && <ErrorNotice error={timeline.error} />}
        {timeline.data && timeline.data.length === 0 && (
          <p className="mt-2 text-[var(--muted)]">Nothing has happened on this case yet.</p>
        )}
        {timeline.data && timeline.data.length > 0 && (
          <ul className="mt-2 flex flex-col gap-1">
            {timeline.data.map((event) => (
              <li key={event.id} className="flex flex-wrap items-baseline gap-2">
                <span className="font-mono text-xs">{event.event_type}</span>
                <span className="text-xs text-[var(--muted)]">
                  {formatDateTime(event.created_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <p className="text-[var(--muted)]">
        The plain-language summary of where the money went is written by the analysis pipeline and
        arrives with Phase 6.
      </p>
    </div>
  )
}

export function CaseDetailPage() {
  const { caseId = '' } = useParams()
  const { user } = useAuth()
  const details = useCase(caseId)

  if (details.isPending) return <Spinner label="Loading case…" />
  if (details.isError)
    return <ErrorNotice error={details.error} onRetry={() => void details.refetch()} />

  const item = details.data

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline gap-3">
        <Link to="/" className="text-[var(--muted)]">
          ← Cases
        </Link>
        <h1 className="text-lg font-semibold">
          {item.case_number} · {item.title}
        </h1>
        <span className={`risk-${item.priority} rounded border px-1.5 py-0.5 text-xs font-medium`}>
          {item.priority}
        </span>
        <span className="text-xs tracking-wide text-[var(--muted)] uppercase">{item.status}</span>
        {canEdit(user) && (
          <Link to={`/cases/${caseId}/address`} className="ml-auto">
            <Button variant="secondary">Add address</Button>
          </Link>
        )}
      </div>

      <HeaderCards />

      <Tabs
        tabs={[
          { id: 'overview', label: 'Overview', render: () => <Overview caseId={caseId} /> },
          {
            id: 'graph',
            label: 'Graph',
            render: () => <LaterPhase what="The fund-flow graph" phase="Phase 5" />,
          },
          {
            id: 'transactions',
            label: 'Transactions',
            render: () => <LaterPhase what="The transactions table" phase="Phase 3" />,
          },
          {
            id: 'patterns',
            label: 'Patterns',
            render: () => <LaterPhase what="Pattern detection" phase="Phase 5" />,
          },
          {
            id: 'attribution',
            label: 'Attribution',
            render: () => <LaterPhase what="Entity attribution" phase="Phase 6" />,
          },
          {
            id: 'evidence',
            label: 'Evidence',
            render: () => <LaterPhase what="The evidence ledger" phase="Phase 3" />,
          },
        ]}
      />
    </div>
  )
}
