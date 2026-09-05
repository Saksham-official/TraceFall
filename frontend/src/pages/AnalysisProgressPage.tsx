import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { useAnalysis, useCancelAnalysis } from '../api/queries'
import type { Analysis } from '../api/types'
import { Banner, Button, Card, ErrorNotice, Spinner } from '../components/ui'
import { formatElapsed } from '../lib/format'
import { STAGE_LABEL, STAGE_MARK, deriveStages } from '../lib/stages'

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

const TERMINAL_BANNER: Record<string, { tone: 'info' | 'warning' | 'error'; title: string }> = {
  COMPLETED: { tone: 'info', title: 'Analysis complete' },
  PARTIAL: { tone: 'warning', title: 'Analysis completed with degraded stages' },
  FAILED: { tone: 'error', title: 'Analysis failed' },
  CANCELLED: { tone: 'warning', title: 'Analysis cancelled' },
}

export function AnalysisProgressPage() {
  const { runId = '' } = useParams()
  const analysis = useAnalysis(runId)
  const cancel = useCancelAnalysis(runId)
  const elapsed = useElapsed(analysis.data)

  if (analysis.isPending) return <Spinner label="Loading analysis…" />
  if (analysis.isError)
    return <ErrorNotice error={analysis.error} onRetry={() => void analysis.refetch()} />

  const run = analysis.data
  const stages = deriveStages(run)
  const active = run.status === 'QUEUED' || run.status === 'RUNNING'
  const banner = TERMINAL_BANNER[run.status]

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-lg font-semibold">Analysis</h1>
        <span
          className="text-xs font-medium tracking-wide text-[var(--muted)] uppercase"
          data-testid="analysis-status"
        >
          {run.status}
        </span>
        {elapsed !== null && (
          <span className="ml-auto text-[var(--muted)] tabular-nums">
            elapsed {formatElapsed(elapsed)}
          </span>
        )}
      </div>

      {run.status === 'QUEUED' && (
        <Banner tone="info" title="Queued">
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

      <Card>
        <label className="flex items-center gap-3 text-xs text-[var(--muted)]">
          <span className="sr-only">Progress</span>
          <progress
            className="w-full"
            value={run.progress_pct}
            max={100}
            aria-label={`Analysis progress ${run.progress_pct} percent`}
          />
          <span className="tabular-nums">{run.progress_pct}%</span>
        </label>

        <ol className="mt-3 flex flex-col gap-1">
          {stages.map((stage) => {
            const mark = STAGE_MARK[stage.state]
            return (
              <li key={stage.name} className="flex items-baseline gap-2">
                <span aria-hidden="true" className="w-4 text-center">
                  {mark.glyph}
                </span>
                <span
                  className={
                    stage.state === 'PENDING' || stage.state === 'SKIPPED'
                      ? 'text-[var(--muted)]'
                      : ''
                  }
                >
                  {STAGE_LABEL[stage.name]}
                </span>
                <span className="text-xs text-[var(--muted)]">{mark.word}</span>
                {stage.durationMs !== null && (
                  <span className="text-xs text-[var(--muted)] tabular-nums">
                    {(stage.durationMs / 1000).toFixed(1)}s
                  </span>
                )}
                {stage.detail && (
                  <span className="text-xs text-[var(--muted)]">· {stage.detail}</span>
                )}
              </li>
            )
          })}
        </ol>
      </Card>

      {cancel.isError && <ErrorNotice error={cancel.error} />}

      <div className="flex flex-wrap items-center gap-2">
        {active && (
          <Button variant="secondary" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
            {cancel.isPending ? 'Cancelling…' : 'Cancel'}
          </Button>
        )}
        <Link to={`/cases/${run.case_id}`} className="ml-auto">
          <Button variant="ghost">Open case</Button>
        </Link>
        {(run.status === 'COMPLETED' || run.status === 'PARTIAL') && (
          <Link to={`/analyses/${run.id}/investigation`}>
            <Button>Open findings →</Button>
          </Link>
        )}
      </div>
    </div>
  )
}
