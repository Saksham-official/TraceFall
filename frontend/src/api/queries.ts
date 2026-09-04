/** TanStack Query bindings for the endpoints that exist today. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { query, request } from './client'
import type {
  Analysis,
  AnalysisAccepted,
  AnalysisStart,
  Case,
  CaseAddress,
  CaseAddressCreate,
  CaseCreate,
  CaseStatus,
  Health,
  Page,
  Priority,
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
  analysis: (id: string) => ['analysis', id] as const,
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
