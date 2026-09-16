import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { useAnalysis, useCancelAnalysis } from '../api/queries'
import type { Analysis } from '../api/types'
import { AddressChip } from '../components/AddressChip'
import {
  AlertTriangleIcon,
  ArrowRightIcon,
  CheckIcon,
  ClockIcon,
  DashIcon,
  SpinnerIcon,
  XIcon,
} from '../components/icons'
import {
  Banner,
  Button,
  Card,
  ErrorNotice,
  Skeleton,
  StatusPill,
} from '../components/ui'
import { formatElapsed } from '../lib/format'
import { STAGE_LABEL, STAGE_MARK, deriveStages } from '../lib/stages'
import type { StageState } from '../lib/stages'

function useElapsed(run: Analysis | undefined): number | null {
  const [now, setNow] = useState(() => Date.now())
  const ticking = run !== undefined && (run.status === 'QUEUED' || run.status === 'RUNNING')

  useEffect(() => {
    if (!ticking) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [ticking])

  if (!run?.started_at) return null
  const end = run.completed_at ? new Date(run.completed_at).getTime() : now
  return (end - new Date(run.started_at).getTime()) / 1000
}

const TERMINAL_BANNER: Record<string, { tone: 'success' | 'warning' | 'error'; title: string }> = {
  COMPLETED: { tone: 'success', title: 'Analysis complete' },
  PARTIAL: { tone: 'warning', title: 'Analysis completed with degraded stages' },
  FAILED: { tone: 'error', title: 'Analysis failed' },
  CANCELLED: { tone: 'warning', title: 'Analysis cancelled' },
}

/** The glyph is decoration; `STAGE_MARK.word` beside it carries the meaning. */
const STAGE_ICON: Record<StageState, { Icon: typeof CheckIcon; cls: string }> = {
  PENDING: { Icon: DashIcon, cls: 'border-[var(--border)] text-[var(--muted)]' },
  RUNNING: {
    Icon: SpinnerIcon,
    cls: 'border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)] pulse-ring',
  },
  COMPLETED: {
    Icon: CheckIcon,
    cls: 'border-[var(--success-border)] bg-[var(--success-bg)] text-[var(--success-fg)]',
  },
  DEGRADED: {
    Icon: AlertTriangleIcon,
    cls: 'border-[var(--warning-border)] bg-[var(--warning-bg)] text-[var(--warning-fg)]',
  },
  FAILED: {
    Icon: XIcon,
    cls: 'border-[var(--danger-border)] bg-[var(--danger-bg)] text-[var(--danger-fg)]',
  },
  SKIPPED: { Icon: DashIcon, cls: 'border-[var(--border)] text-[var(--muted)]' },
}

export function AnalysisProgressPage() {
  const { runId = '' } = useParams()
  const analysis = useAnalysis(runId)
  const cancel = useCancelAnalysis(runId)
  const elapsed = useElapsed(analysis.data)

  if (analysis.isPending) {
    return (
      <div role="status" aria-label="Loading analysis" className="mx-auto flex max-w-2xl flex-col gap-4">
        <Skeleton className="h-7 w-1/2" />
        <Skeleton className="h-64" />
      </div>
    )
  }
  if (analysis.isError)
    return <ErrorNotice error={analysis.error} onRetry={() => void analysis.refetch()} />

  const run = analysis.data
  const stages = deriveStages(run)
  const active = run.status === 'QUEUED' || run.status === 'RUNNING'
  const banner = TERMINAL_BANNER[run.status]
  const finished = run.status === 'COMPLETED' || run.status === 'PARTIAL'
  const done = stages.filter((s) => s.state === 'COMPLETED' || s.state === 'DEGRADED').length

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5">
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-h1">Analysis</h1>
          <StatusPill status={run.status} data-testid="analysis-status" />
          {elapsed !== null && (
            <span className="text-num ml-auto inline-flex items-center gap-1.5 text-[var(--muted)]">
              <ClockIcon />
              {formatElapsed(elapsed)}
            </span>
          )}
        </div>
        {run.root_address && run.root_chain && (
          <div className="mt-2">
            <AddressChip address={run.root_address} chain={run.root_chain} size="lg" />
          </div>
        )}
      </div>

      {run.status === 'QUEUED' && (
        <Banner tone="info" title="Queued" compact>
          <p>Waiting for a worker to pick this run up.</p>
        </Banner>
      )}

      {banner && (
        <Banner tone={banner.tone} title={banner.title}>
          {run.status === 'FAILED' && (
            <p>{run.error ?? 'The pipeline stopped before it produced a result.'}</p>
          )}
          {run.status === 'PARTIAL' && (
            <>
              <p>
                Some stages did not complete. What is shown below is smaller than a full answer,
                and knowing that is part of the answer.
              </p>
              <ul className="mt-1 list-disc pl-5">
                {run.degradations.map((degradation, index) => (
                  <li key={index}>
                    {[degradation.stage, degradation.reason].filter(Boolean).join(' — ') ||
                      'Stage degraded; the backend gave no reason.'}
                  </li>
                ))}
              </ul>
            </>
          )}
        </Banner>
      )}

      <Card padding="none">
        <div className="border-b border-[var(--border)] px-4 py-3">
          <div className="mb-2 flex items-center justify-between text-xs">
            <span className="text-label">
              {active ? 'Pipeline running' : 'Pipeline'} · stage {Math.min(done + 1, stages.length)} of{' '}
              {stages.length}
            </span>
            <span className="text-num font-medium">{run.progress_pct}%</span>
          </div>
          <div
            role="progressbar"
            aria-label="Analysis progress"
            aria-valuenow={run.progress_pct}
            aria-valuemin={0}
            aria-valuemax={100}
            className="h-1.5 overflow-hidden rounded-full bg-[var(--surface-3)]"
          >
            <div
              className={`h-full rounded-full transition-[width] duration-700 ease-out ${
                run.status === 'FAILED'
                  ? 'bg-[var(--danger-fg)]'
                  : run.status === 'PARTIAL'
                    ? 'bg-[var(--warning-border)]'
                    : 'bg-[var(--accent)]'
              }`}
              style={{ width: `${run.progress_pct}%` }}
            />
          </div>
        </div>

        <ol className="px-4 py-2">
          {stages.map((stage, index) => {
            const mark = STAGE_MARK[stage.state]
            const { Icon, cls } = STAGE_ICON[stage.state]
            const dim = stage.state === 'PENDING' || stage.state === 'SKIPPED'
            return (
              <li key={stage.name} className="relative flex items-start gap-3 py-2">
                {index < stages.length - 1 && (
                  <span
                    aria-hidden="true"
                    className="absolute top-8 left-[0.8125rem] h-[calc(100%-1.25rem)] w-px bg-[var(--border)]"
                  />
                )}
                <span
                  aria-hidden="true"
                  className={`relative z-10 flex h-[1.65rem] w-[1.65rem] shrink-0 items-center justify-center rounded-full border bg-[var(--surface)] ${cls}`}
                >
                  <Icon className="h-3.5 w-3.5" />
                </span>
                <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-2 pt-1">
                  <span className={dim ? 'text-[var(--muted)]' : 'font-medium'}>
                    {STAGE_LABEL[stage.name]}
                  </span>
                  <span className="text-meta">{mark.word}</span>
                  {stage.durationMs !== null && (
                    <span className="text-meta text-num">{(stage.durationMs / 1000).toFixed(1)}s</span>
                  )}
                  {stage.detail && <span className="text-meta">· {stage.detail}</span>}
                </div>
              </li>
            )
          })}
        </ol>
      </Card>

      {cancel.isError && <ErrorNotice error={cancel.error} />}

      <div className="flex flex-wrap items-center gap-2">
        {active && (
          <Button variant="secondary" onClick={() => cancel.mutate()} loading={cancel.isPending}>
            {cancel.isPending ? 'Cancelling…' : 'Cancel'}
          </Button>
        )}
        <Link to={`/cases/${run.case_id}`} className="ml-auto">
          <Button variant="ghost">Open case</Button>
        </Link>
        {finished && (
          <Link to={`/analyses/${run.id}/investigation`}>
            <Button icon={<ArrowRightIcon />}>Open findings</Button>
          </Link>
        )}
      </div>
    </div>
  )
}
