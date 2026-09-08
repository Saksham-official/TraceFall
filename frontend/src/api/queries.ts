/** TanStack Query bindings for the endpoints that exist today. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { query, request } from './client'
import type {
  Alert,
  Analysis,
  AttributionRow,
  AnalysisAccepted,
  AnalysisStart,
  Case,
  CaseAddress,
  FreezeRequest,
  CaseAddressCreate,
  CaseCreate,
  CaseStatus,
  Correlations,
  GraphPayload,
  Health,
  Page,
  PatternRow,
  Priority,
  ReportRow,
  RiskPayload,
  TimelineEvent,
  User,
} from './types'

export const keys = {
  me: ['me'] as const,
  health: ['health'] as const,
  cases: (filters: CaseFilters) => ['cases', filters] as const,
  case: (id: string) => ['case', id] as const,
  caseAddresses: (id: string) => ['case', id, 'addresses'] as const,
  caseAnalyses: (id: string) => ['case', id, 'analyses'] as const,
  caseTimeline: (id: string) => ['case', id, 'timeline'] as const,
  caseCorrelations: (id: string) => ['case', id, 'correlations'] as const,
  analysis: (id: string) => ['analysis', id] as const,
  freezeRequest: (id: string) => ['analysis', id, 'freeze-request'] as const,
}

export interface CaseFilters {
  status?: CaseStatus | ''
  priority?: Priority | ''
  q?: string
}

export function useMe(enabled: boolean) {
  return useQuery({
    queryKey: keys.me,
    queryFn: () => request<User>('/auth/me'),
    enabled,
    retry: false,
  })
}

export function useHealth() {
  return useQuery({
    queryKey: keys.health,
    queryFn: () => request<Health>('/health'),
    staleTime: 60_000,
  })
}

export function useCases(filters: CaseFilters) {
  return useQuery({
    queryKey: keys.cases(filters),
    queryFn: () =>
      request<Page<Case>>(
        `/cases${query({ status: filters.status, priority: filters.priority, q: filters.q })}`,
      ),
  })
}

export function useCase(id: string) {
  return useQuery({ queryKey: keys.case(id), queryFn: () => request<Case>(`/cases/${id}`) })
}

export function useCaseAddresses(id: string) {
  return useQuery({
    queryKey: keys.caseAddresses(id),
    queryFn: () => request<CaseAddress[]>(`/cases/${id}/addresses`),
  })
}

export function useCaseAnalyses(id: string) {
  return useQuery({
    queryKey: keys.caseAnalyses(id),
    queryFn: () => request<Analysis[]>(`/cases/${id}/analyses`),
  })
}

export function useCaseTimeline(id: string) {
  return useQuery({
    queryKey: keys.caseTimeline(id),
    queryFn: () => request<TimelineEvent[]>(`/cases/${id}/timeline`),
  })
}

export const ANALYSIS_IS_ACTIVE = (status: Analysis['status']): boolean =>
  status === 'QUEUED' || status === 'RUNNING'

export function useAnalysis(id: string) {
  return useQuery({
    queryKey: keys.analysis(id),
    queryFn: () => request<Analysis>(`/analyses/${id}`),
    // Poll only while the run can still change (FR-121).
    refetchInterval: (q) => (q.state.data && ANALYSIS_IS_ACTIVE(q.state.data.status) ? 2000 : false),
  })
}

export function useCreateCase() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (payload: CaseCreate) =>
      request<Case>('/cases', { method: 'POST', body: payload }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['cases'] }),
  })
}

export function useAddAddress(caseId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (payload: CaseAddressCreate) =>
      request<CaseAddress>(`/cases/${caseId}/addresses`, { method: 'POST', body: payload }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.caseAddresses(caseId) }),
  })
}

export function useStartAnalysis(caseId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (payload: AnalysisStart) =>
      request<AnalysisAccepted>(`/cases/${caseId}/analyses`, { method: 'POST', body: payload }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.caseAnalyses(caseId) }),
  })
}

export function useCancelAnalysis(runId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => request<Analysis>(`/analyses/${runId}/cancel`, { method: 'POST' }),
    onSuccess: (data) => client.setQueryData(keys.analysis(runId), data),
  })
}

// --- analysis results ---------------------------------------------------------

export const resultKeys = {
  graph: (runId: string, maxNodes: number) => ['analysis', runId, 'graph', maxNodes] as const,
  attributions: (runId: string) => ['analysis', runId, 'attributions'] as const,
  patterns: (runId: string) => ['analysis', runId, 'patterns'] as const,
  risk: (runId: string) => ['analysis', runId, 'risk'] as const,
  reports: (caseId: string) => ['case', caseId, 'reports'] as const,
}

export function useGraph(runId: string, maxNodes = 500, enabled = true) {
  return useQuery({
    queryKey: resultKeys.graph(runId, maxNodes),
    queryFn: () => request<GraphPayload>(`/analyses/${runId}/graph?max_nodes=${maxNodes}`),
    enabled,
  })
}

export function useAttributions(runId: string, enabled = true) {
  return useQuery({
    queryKey: resultKeys.attributions(runId),
    queryFn: () => request<AttributionRow[]>(`/analyses/${runId}/attributions`),
    enabled,
  })
}

export function usePatterns(runId: string, enabled = true) {
  return useQuery({
    queryKey: resultKeys.patterns(runId),
    queryFn: () => request<PatternRow[]>(`/analyses/${runId}/patterns`),
    enabled,
  })
}

export function useRisk(runId: string, enabled = true) {
  return useQuery({
    queryKey: resultKeys.risk(runId),
    queryFn: () => request<RiskPayload>(`/analyses/${runId}/risk`),
    enabled,
  })
}

export function useReports(caseId: string) {
  return useQuery({
    queryKey: resultKeys.reports(caseId),
    queryFn: () => request<ReportRow[]>(`/cases/${caseId}/reports`),
  })
}

export function useGenerateReport(caseId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: { analysis_run_id: string; format?: 'PDF' | 'JSON' | 'CSV' }) =>
      request<ReportRow>(`/cases/${caseId}/reports`, { method: 'POST', body }),
    onSuccess: () => client.invalidateQueries({ queryKey: resultKeys.reports(caseId) }),
  })
}

// --- alerts -------------------------------------------------------------------

export const alertKeys = {
  open: ['alerts', 'open'] as const,
  forCase: (caseId: string) => ['case', caseId, 'alerts'] as const,
}

/** Unacknowledged alerts across every case the user may see (FR-101). */
export function useOpenAlerts() {
  return useQuery({
    queryKey: alertKeys.open,
    queryFn: () => request<Page<Alert>>('/alerts?unacknowledged=true'),
  })
}

export function useCaseCorrelations(caseId: string) {
  return useQuery({
    queryKey: keys.caseCorrelations(caseId),
    queryFn: () => request<Correlations>(`/cases/${caseId}/correlations`),
  })
}

export function useCaseAlerts(caseId: string) {
  return useQuery({
    queryKey: alertKeys.forCase(caseId),
    queryFn: () => request<Page<Alert>>(`/cases/${caseId}/alerts`),
  })
}

export function useAcknowledgeAlert() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => request<Alert>(`/alerts/${id}/acknowledge`, { method: 'POST' }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['alerts'] }),
  })
}

export function useFreezeRequest(runId: string) {
  return useQuery({
    queryKey: keys.freezeRequest(runId),
    queryFn: () => request<FreezeRequest>(`/analyses/${runId}/freeze-request`),
  })
}
