import { useDeferredValue, useState } from 'react'
import { Link } from 'react-router-dom'

import { useCases, useOpenAlerts } from '../api/queries'
import { CASE_STATUSES, PRIORITIES } from '../api/types'
import type { Case, CaseStatus, Priority } from '../api/types'
import { canEdit, useAuth } from '../auth'
import { AlertsPanel } from '../components/AlertsPanel'
import {
  ActivityIcon,
  AlertTriangleIcon,
  BellIcon,
  FolderIcon,
  PlusIcon,
  SearchIcon,
} from '../components/icons'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorNotice,
  PageHeader,
  Select,
  Skeleton,
  StatTile,
  StatusPill,
  TextInput,
} from '../components/ui'
import { formatInr, relativeTime } from '../lib/format'

const ROW_GRID = 'grid grid-cols-[7.5rem_5.5rem_1fr] sm:grid-cols-[7.5rem_5.5rem_6.5rem_1fr_7rem_6rem]'

function CaseRow({ item }: { item: Case }) {
  const loss = formatInr(item.reported_loss_inr)
  return (
    <li className="border-b border-[var(--border)] last:border-b-0">
      <Link
        to={`/cases/${item.id}`}
        className={`${ROW_GRID} transition-ui items-center gap-x-3 px-4 py-2.5 hover:bg-[var(--surface-2)] focus-visible:bg-[var(--surface-2)]`}
      >
        <span className="font-mono text-[0.8125rem] font-medium">{item.case_number}</span>
        {/* Priority carries its word as well as its colour — never the colour alone (NFR-18). */}
        <Badge band={item.priority} size="xs" className="justify-self-start">
          {item.priority}
        </Badge>
        <span className="hidden justify-self-start sm:block">
          <StatusPill status={item.status} />
        </span>
        <span className="col-span-3 truncate pt-1 sm:col-span-1 sm:pt-0">{item.title}</span>
        <span className="text-num hidden text-right text-[var(--muted)] sm:block">{loss ?? '—'}</span>
        <span className="text-meta hidden text-right sm:block">{relativeTime(item.created_at)}</span>
      </Link>
    </li>
  )
}

function RowsSkeleton() {
  return (
    <div role="status" aria-label="Loading cases" className="divide-y divide-[var(--border)]">
      {Array.from({ length: 6 }, (_, index) => (
        <div key={index} className={`${ROW_GRID} items-center gap-x-3 px-4 py-3`}>
          <Skeleton className="h-3.5 w-24" />
          <Skeleton className="h-4 w-14" />
          <Skeleton className="hidden h-4 w-16 sm:block" />
          <Skeleton className="h-3.5 w-2/3" />
          <Skeleton className="hidden h-3.5 w-16 justify-self-end sm:block" />
          <Skeleton className="hidden h-3.5 w-12 justify-self-end sm:block" />
        </div>
      ))}
    </div>
  )
}

export function DashboardPage() {
  const { user } = useAuth()
  const [status, setStatus] = useState<CaseStatus | ''>('')
  const [priority, setPriority] = useState<Priority | ''>('')
  const [search, setSearch] = useState('')
  const q = useDeferredValue(search)

  const cases = useCases({ status, priority, q })
  const alerts = useOpenAlerts()
  const items = cases.data?.items ?? []
  const filtered = status !== '' || priority !== '' || q !== ''

  // Computed from the page in view — the API returns the most recent page, not totals.
  const open = items.filter((item) => item.status === 'OPEN' || item.status === 'ANALYSING').length
  const analysing = items.filter((item) => item.status === 'ANALYSING').length
  const urgent = items.filter((item) => item.priority === 'HIGH' || item.priority === 'CRITICAL').length
  const openAlerts = alerts.data?.items.length

  const newCase = canEdit(user) ? (
    <Link to="/cases/new">
      <Button icon={<PlusIcon />}>New case</Button>
    </Link>
  ) : undefined

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Cases"
        description="Each case holds one investigation: a suspect address, its analysis runs, and the report."
        actions={newCase}
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Open cases"
          value={cases.isPending ? <Skeleton className="h-6 w-10" /> : open}
          hint={filtered ? 'in the filtered view' : 'in view'}
          icon={<FolderIcon className="h-4 w-4" />}
        />
        <StatTile
          label="Analysing now"
          value={cases.isPending ? <Skeleton className="h-6 w-10" /> : analysing}
          hint="pipeline runs in progress"
          tone={analysing > 0 ? 'info' : 'neutral'}
          icon={<ActivityIcon className="h-4 w-4" />}
        />
        <StatTile
          label="High or critical priority"
          value={cases.isPending ? <Skeleton className="h-6 w-10" /> : urgent}
          hint="cases needing attention first"
          tone={urgent > 0 ? 'warning' : 'neutral'}
          icon={<AlertTriangleIcon className="h-4 w-4" />}
        />
        <StatTile
          label="Open alerts"
          value={alerts.isPending ? <Skeleton className="h-6 w-10" /> : (openAlerts ?? '—')}
          hint="unacknowledged, across your cases"
          tone={openAlerts ? 'danger' : 'neutral'}
          icon={<BellIcon className="h-4 w-4" />}
        />
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <Card padding="none" className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border)] p-3">
            <label className="relative min-w-56 flex-1">
              <span className="sr-only">Search</span>
              <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-[var(--muted)]" />
              <TextInput
                type="search"
                value={search}
                placeholder="Case number, NCRP or FIR reference, or title"
                title="Case number, NCRP or FIR reference, or title."
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8"
              />
            </label>
            <label className="flex items-center gap-2">
              <span className="text-secondary text-[var(--muted)]">Status</span>
              <Select
                value={status}
                className="w-36"
                onChange={(e) => setStatus(e.target.value as CaseStatus | '')}
              >
                <option value="">Any</option>
                {CASE_STATUSES.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </Select>
            </label>
            <label className="flex items-center gap-2">
              <span className="text-secondary text-[var(--muted)]">Priority</span>
              <Select
                value={priority}
                className="w-36"
                onChange={(e) => setPriority(e.target.value as Priority | '')}
              >
                <option value="">Any</option>
                {PRIORITIES.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </Select>
            </label>
          </div>

          <div
            className={`${ROW_GRID} text-label items-center gap-x-3 border-b border-[var(--border)] bg-[var(--surface-2)]/60 px-4 py-2`}
            aria-hidden="true"
          >
            <span>Case</span>
            <span>Priority</span>
            <span className="hidden sm:block">Status</span>
            <span>Title</span>
            <span className="hidden text-right sm:block">Reported loss</span>
            <span className="hidden text-right sm:block">Created</span>
          </div>

          {cases.isPending && <RowsSkeleton />}
          {cases.isError && (
            <div className="p-3">
              <ErrorNotice error={cases.error} onRetry={() => void cases.refetch()} />
            </div>
          )}

          {cases.isSuccess &&
            (items.length === 0 ? (
              <div className="p-3">
                {filtered ? (
                  <EmptyState title="No cases match these filters" icon={<SearchIcon />}>
                    <p>Clear the search or widen the status and priority filters.</p>
                  </EmptyState>
                ) : (
                  <EmptyState title="No cases yet" icon={<FolderIcon />} action={newCase}>
                    <p>
                      A case holds one investigation. Create one, add the suspect address the
                      victim reported, then start an analysis to trace where the funds went.
                    </p>
                  </EmptyState>
                )}
              </div>
            ) : (
              <>
                <ul>
                  {items.map((item) => (
                    <CaseRow key={item.id} item={item} />
                  ))}
                </ul>
                {cases.data.has_more && (
                  <p className="text-meta border-t border-[var(--border)] px-4 py-2">
                    Showing the {items.length} most recent cases. Narrow the filters to find older
                    ones.
                  </p>
                )}
              </>
            ))}
        </Card>

        <AlertsPanel className="self-start xl:sticky xl:top-[4.5rem]" />
      </div>
    </div>
  )
}
