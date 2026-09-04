/**
 * The stage list for the progress screen (FRONTEND_SPEC §6).
 *
 * `GET /analyses/{id}` returns `stages: []` today — `AnalysisRun` has no per-stage column,
 * so the response carries only the current `stage` and the run `status`. This derives the
 * list from those two, and steps aside the moment the backend starts sending real rows.
 */

import { ANALYSIS_STAGES } from '../api/types'
import type { Analysis, AnalysisStage, StageOut } from '../api/types'

export type StageState = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'DEGRADED' | 'FAILED' | 'SKIPPED'

export interface DerivedStage {
  name: AnalysisStage
  state: StageState
  detail: string | null
  durationMs: number | null
}

const KNOWN_STATES: StageState[] = [
  'PENDING',
  'RUNNING',
  'COMPLETED',
  'DEGRADED',
  'FAILED',
  'SKIPPED',
]

function fromServer(stage: StageOut): DerivedStage {
  const state = stage.status.toUpperCase() as StageState
  return {
    name: stage.name,
    state: KNOWN_STATES.includes(state) ? state : 'PENDING',
    detail: stage.detail,
    durationMs: stage.duration_ms,
  }
}

export function deriveStages(run: Pick<Analysis, 'status' | 'stage' | 'stages' | 'degradations'>) {
  if (run.stages.length > 0) return run.stages.map(fromServer)

  const degraded = new Set(
    run.degradations.map((d) => (typeof d?.stage === 'string' ? d.stage : '')).filter(Boolean),
  )
  const current = run.stage ? ANALYSIS_STAGES.indexOf(run.stage) : -1

  return ANALYSIS_STAGES.map((name, index): DerivedStage => {
    const base = { name, detail: null, durationMs: null }
    if (degraded.has(name)) return { ...base, state: 'DEGRADED' }

    switch (run.status) {
      case 'QUEUED':
        return { ...base, state: 'PENDING' }
      case 'COMPLETED':
      case 'PARTIAL':
        return { ...base, state: 'COMPLETED' }
      case 'RUNNING':
        if (current === -1) return { ...base, state: 'PENDING' }
        if (index < current) return { ...base, state: 'COMPLETED' }
        return { ...base, state: index === current ? 'RUNNING' : 'PENDING' }
      case 'FAILED':
        if (index < current) return { ...base, state: 'COMPLETED' }
        return { ...base, state: index === current ? 'FAILED' : 'SKIPPED' }
      case 'CANCELLED':
        if (index < current) return { ...base, state: 'COMPLETED' }
        return { ...base, state: 'SKIPPED' }
    }
  })
}

/** Glyph plus word — the glyph is decoration, the word carries the meaning. */
export const STAGE_MARK: Record<StageState, { glyph: string; word: string }> = {
  PENDING: { glyph: '○', word: 'not started' },
  RUNNING: { glyph: '◐', word: 'running' },
  COMPLETED: { glyph: '✓', word: 'done' },
  DEGRADED: { glyph: '!', word: 'degraded' },
  FAILED: { glyph: '✕', word: 'failed' },
  SKIPPED: { glyph: '–', word: 'not run' },
}

export const STAGE_LABEL: Record<AnalysisStage, string> = {
  RETRIEVAL: 'Retrieving blockchain data',
  NORMALIZATION: 'Normalizing transactions',
  ENRICHMENT: 'Enriching addresses',
  TRACING: 'Tracing fund flows',
  GRAPH: 'Building graph',
  PATTERNS: 'Detecting patterns',
  ATTRIBUTION: 'Attributing entities',
  RISK: 'Scoring risk',
  ALERTS: 'Raising alerts',
}
