import { useDeferredValue, useState } from 'react'
import { Link } from 'react-router-dom'

import { useCases } from '../api/queries'
import { CASE_STATUSES, PRIORITIES } from '../api/types'
import type { Case, CaseStatus, Priority } from '../api/types'
import { canEdit, useAuth } from '../auth'
import { AlertsPanel } from '../components/AlertsPanel'
import {
  Button,
  Card,
  EmptyState,
  ErrorNotice,
  Field,
  Select,
  Spinner,
  TextInput,
} from '../components/ui'
import { formatInr, relativeTime } from '../lib/format'

/** Priority carries its word as well as its colour — never the colour alone (NFR-18). */
function PriorityTag({ priority }: { priority: Priority }) {
  return (
    <span className={`risk-${priority} rounded border px-1.5 py-0.5 text-xs font-medium`}>
      {priority}
    </span>
  )
}

function CaseRow({ item }: { item: Case }) {
  const loss = formatInr(item.reported_loss_inr)
  return (
    <li className="border-b border-[var(--border)] last:border-b-0">
      <Link
        to={`/cases/${item.id}`}
        className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-2 hover:bg-[var(--surface-2)]"
      >
        <span className="font-mono font-medium">{item.case_number}</span>
        <PriorityTag priority={item.priority} />
        <span className="text-xs tracking-wide text-[var(--muted)] uppercase">{item.status}</span>
        <span className="w-full sm:w-auto sm:flex-1">{item.title}</span>
        {loss && <span className="text-[var(--muted)] tabular-nums">{loss}</span>}
        <span className="text-xs text-[var(--muted)]">{relativeTime(item.created_at)}</span>
      </Link>
    </li>
  )
}

export function DashboardPage() {
  const { user } = useAuth()
  const [status, setStatus] = useState<CaseStatus | ''>('')
  const [priority, setPriority] = useState<Priority | ''>('')
  const [search, setSearch] = useState('')
  const q = useDeferredValue(search)

  const cases = useCases({ status, priority, q })
  const items = cases.data?.items ?? []
  const filtered = status !== '' || priority !== '' || q !== ''

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold">Cases</h1>
        {canEdit(user) && (
          <Link to="/cases/new" className="ml-auto">
            <Button>+ New case</Button>
          </Link>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <div className="flex flex-col gap-3">
          <Card className="flex flex-wrap items-end gap-3">
            <div className="min-w-56 flex-1">
              <Field label="Search" hint="Case number, NCRP or FIR reference, or title.">
                {(props) => (
                  <TextInput
                    {...props}
                    type="search"
                    value={search}
                    placeholder="TF-2026-0142"
                    onChange={(e) => setSearch(e.target.value)}
                  />
                )}
              </Field>
            </div>
            <Field label="Status">
              {(props) => (
                <Select
                  {...props}
                  value={status}
                  onChange={(e) => setStatus(e.target.value as CaseStatus | '')}
                >
                  <option value="">Any</option>
                  {CASE_STATUSES.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Priority">
              {(props) => (
                <Select
                  {...props}
                  value={priority}
                  onChange={(e) => setPriority(e.target.value as Priority | '')}
                >
                  <option value="">Any</option>
                  {PRIORITIES.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </Card>

          {cases.isPending && <Spinner label="Loading cases…" />}
          {cases.isError && <ErrorNotice error={cases.error} onRetry={() => void cases.refetch()} />}

          {cases.isSuccess &&
            (items.length === 0 ? (
              filtered ? (
                <EmptyState title="No cases match these filters">
                  <p>Clear the search or widen the status and priority filters.</p>
                </EmptyState>
              ) : (
                <EmptyState
                  title="No cases yet"
                  action={
                    canEdit(user) ? (
                      <Link to="/cases/new">
                        <Button>+ New case</Button>
                      </Link>
                    ) : undefined
                  }
                >
                  <p>
                    A case holds one investigation. Create one, add the suspect address the victim
                    reported, then start an analysis to trace where the funds went.
                  </p>
                </EmptyState>
              )
            ) : (
              <Card padding="none">
                <ul>
                  {items.map((item) => (
                    <CaseRow key={item.id} item={item} />
                  ))}
                </ul>
                {cases.data.has_more && (
                  <p className="border-t border-[var(--border)] px-3 py-2 text-xs text-[var(--muted)]">
                    Showing the {items.length} most recent cases. Narrow the filters to find older
                    ones.
                  </p>
                )}
              </Card>
            ))}
        </div>

        <AlertsPanel />
      </div>
    </div>
  )
}
