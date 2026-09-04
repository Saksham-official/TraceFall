import { describe, expect, it } from 'vitest'

import { deriveStages } from './stages'
import type { Analysis } from '../api/types'

type Run = Pick<Analysis, 'status' | 'stage' | 'stages' | 'degradations'>

const run = (overrides: Partial<Run>): Run => ({
  status: 'RUNNING',
  stage: null,
  stages: [],
  degradations: [],
  ...overrides,
})

const stateOf = (list: ReturnType<typeof deriveStages>, name: string) =>
  list.find((stage) => stage.name === name)?.state

describe('deriveStages', () => {
  it('marks everything pending while queued', () => {
    const stages = deriveStages(run({ status: 'QUEUED' }))
    expect(stages.every((stage) => stage.state === 'PENDING')).toBe(true)
  })

  it('splits the list around the running stage', () => {
    const stages = deriveStages(run({ status: 'RUNNING', stage: 'TRACING' }))
    expect(stateOf(stages, 'RETRIEVAL')).toBe('COMPLETED')
    expect(stateOf(stages, 'TRACING')).toBe('RUNNING')
    expect(stateOf(stages, 'GRAPH')).toBe('PENDING')
  })

  it('completes every stage on a completed run, even though the backend clears `stage`', () => {
    const stages = deriveStages(run({ status: 'COMPLETED', stage: null }))
    expect(stages.every((stage) => stage.state === 'COMPLETED')).toBe(true)
  })

  it('shows a failure at the stage that failed and does not claim later stages ran', () => {
    const stages = deriveStages(run({ status: 'FAILED', stage: 'ENRICHMENT' }))
    expect(stateOf(stages, 'NORMALIZATION')).toBe('COMPLETED')
    expect(stateOf(stages, 'ENRICHMENT')).toBe('FAILED')
    expect(stateOf(stages, 'TRACING')).toBe('SKIPPED')
  })

  it('does not mark a cancelled run failed', () => {
    const stages = deriveStages(run({ status: 'CANCELLED', stage: 'TRACING' }))
    expect(stateOf(stages, 'TRACING')).toBe('SKIPPED')
    expect(stages.some((stage) => stage.state === 'FAILED')).toBe(false)
  })

  it('names the degraded stages of a partial run', () => {
    const stages = deriveStages(
      run({ status: 'PARTIAL', stage: null, degradations: [{ stage: 'PATTERNS', reason: 'x' }] }),
    )
    expect(stateOf(stages, 'PATTERNS')).toBe('DEGRADED')
    expect(stateOf(stages, 'RISK')).toBe('COMPLETED')
  })

  it('defers to server-sent stages the moment the backend supplies them', () => {
    const stages = deriveStages(
      run({
        status: 'RUNNING',
        stage: 'TRACING',
        stages: [{ name: 'RETRIEVAL', status: 'COMPLETED', duration_ms: 8420, detail: '412' }],
      }),
    )
    expect(stages).toHaveLength(1)
    expect(stages[0]).toMatchObject({ name: 'RETRIEVAL', state: 'COMPLETED', durationMs: 8420 })
  })
})
