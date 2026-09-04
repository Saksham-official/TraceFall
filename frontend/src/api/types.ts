/**
 * Types mirroring `backend/app/schemas/` and `backend/app/db/models/enums.py`.
 *
 * The backend is the source of truth. Where docs/API_SPEC.md and the implementation
 * disagree, these follow the implementation.
 *
 * Pydantic serialises `Decimal` as a JSON string to preserve precision, so monetary
 * fields arrive as strings. Never parse one into a float on an amount path.
 */

export const USER_ROLES = ['ADMIN', 'INVESTIGATOR', 'ANALYST', 'VIEWER'] as const
export type UserRole = (typeof USER_ROLES)[number]

export const CASE_STATUSES = ['OPEN', 'ANALYSING', 'REVIEW', 'CLOSED'] as const
export type CaseStatus = (typeof CASE_STATUSES)[number]

export const PRIORITIES = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'] as const
export type Priority = (typeof PRIORITIES)[number]

export const ADDRESS_ROLES = ['SUSPECT', 'VICTIM_SOURCE', 'DISCOVERED'] as const
export type AddressRole = (typeof ADDRESS_ROLES)[number]

export const CHAIN_CODES = ['TRON', 'ETHEREUM'] as const
export type ChainCode = (typeof CHAIN_CODES)[number]

export const RISK_BANDS = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'] as const
export type RiskBand = (typeof RISK_BANDS)[number]

/** The product's central integrity distinction. These are never collapsed. */
export const ATTRIBUTION_TIERS = ['CONFIRMED', 'PROBABLE', 'UNATTRIBUTED'] as const
export type AttributionTier = (typeof ATTRIBUTION_TIERS)[number]

export type AttributionMethod = 'DATASET_MATCH' | 'DEPOSIT_HEURISTIC' | 'CLASSIFIER' | 'MANUAL'

export type EntityType =
  | 'EXCHANGE'
  | 'MIXER'
  | 'BRIDGE'
  | 'TOKEN_CONTRACT'
  | 'DEFI'
  | 'GAMBLING'
  | 'SANCTIONED'
  | 'MERCHANT'
  | 'UNKNOWN'

export const ANALYSIS_STATUSES = [
  'QUEUED',
  'RUNNING',
  'COMPLETED',
  'PARTIAL',
  'FAILED',
  'CANCELLED',
] as const
export type AnalysisStatus = (typeof ANALYSIS_STATUSES)[number]

/** Declaration order is the pipeline order; the progress screen relies on it. */
export const ANALYSIS_STAGES = [
  'RETRIEVAL',
  'NORMALIZATION',
  'ENRICHMENT',
  'TRACING',
  'GRAPH',
  'PATTERNS',
  'ATTRIBUTION',
  'RISK',
  'ALERTS',
] as const
export type AnalysisStage = (typeof ANALYSIS_STAGES)[number]

export type TraceDirection = 'FORWARD' | 'BACKWARD'

// --- envelope ---------------------------------------------------------------

export interface ApiErrorBody {
  code: string
  message: string
  field?: string
  request_id: string
}

export interface Page<T> {
  items: T[]
  next_cursor: string | null
  has_more: boolean
}

// --- auth -------------------------------------------------------------------

export interface User {
  id: number
  email: string
  full_name: string
  role: UserRole
  organisation: string | null
  last_login_at: string | null
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user: User
}

// --- cases ------------------------------------------------------------------

export interface Case {
  id: string
  case_number: string
  title: string
  ncrp_reference: string | null
  fir_reference: string | null
  description: string | null
  reported_loss_inr: string | null
  incident_date: string | null
  status: CaseStatus
  priority: Priority
  owner_id: number
  created_at: string
  updated_at: string
  closed_at: string | null
}

export interface CaseCreate {
  title: string
  ncrp_reference?: string | null
  fir_reference?: string | null
  description?: string | null
  reported_loss_inr?: string | null
  incident_date?: string | null
  priority: Priority
}

export interface TimelineEvent {
  id: number
  actor_id: number | null
  event_type: string
  payload: Record<string, unknown>
  created_at: string
}

// --- addresses --------------------------------------------------------------

export interface CrossCaseMatch {
  case_id: string
  case_number: string
  owner_id: number
}

export interface CaseAddressCreate {
  address: string
  chain?: ChainCode | null
  role?: AddressRole
  reported_amount?: { value: string; asset_symbol: string } | null
  reported_at?: string | null
  notes?: string | null
}

export interface CaseAddress {
  id: number
  address: string
  display_address: string
  chain: ChainCode
  is_contract: boolean | null
  role: AddressRole
  reported_at: string | null
  added_at: string
  cross_case_matches: CrossCaseMatch[]
}

// --- analyses ---------------------------------------------------------------

export interface AnalysisStart {
  address_id: number
  direction?: TraceDirection
  max_depth?: number
  taint_threshold?: number
  time_window_days?: number
  stop_at_services?: boolean
  include_patterns?: boolean
  include_risk?: boolean
}

export interface StageOut {
  name: AnalysisStage
  status: string
  duration_ms: number | null
  detail: string | null
}

export interface Degradation {
  stage?: string
  reason?: string
}

export interface Analysis {
  id: string
  case_id: string
  status: AnalysisStatus
  stage: AnalysisStage | null
  progress_pct: number
  /** Empty until the pipeline persists per-stage rows; derive the list from `stage`. */
  stages: StageOut[]
  degradations: Degradation[]
  partial_results_available: boolean
  started_at: string | null
  completed_at: string | null
  error: string | null
}

export interface AnalysisAccepted {
  analysis_run_id: string
  status: AnalysisStatus
  poll_url: string
  estimated_seconds: number
}

// --- health -----------------------------------------------------------------

export interface Health {
  status: string
  version: string
  live_mode: boolean
  queue_reachable: boolean
  providers: { name: string; reachable: boolean }[]
}

// --- shapes with no endpoint yet (API_SPEC §1) -------------------------------
// Carried by AmountDisplay and AttributionCard, which exist now because they hold the
// product's integrity rules. Phases 6-8 supply the data.

export interface Amount {
  raw: string
  decimals: number
  display: string
  asset: string
  chain?: ChainCode
  usd_approx?: number | null
}

export interface AttributionEvidence {
  signal: string
  value: number | string | boolean
  detail: string
}

export interface AttributionEntity {
  id?: number
  name: string
  type: EntityType
}

export type Attribution =
  | {
      tier: 'CONFIRMED'
      entity: AttributionEntity
      confidence: number | null
      method: AttributionMethod
      evidence: AttributionEvidence[]
      disclaimer?: string | null
    }
  | {
      tier: 'PROBABLE'
      entity: AttributionEntity
      confidence: number
      method: AttributionMethod
      evidence: AttributionEvidence[]
      disclaimer: string
    }
  | {
      tier: 'UNATTRIBUTED'
      entity: null
      confidence: null
      method?: AttributionMethod | null
      evidence?: AttributionEvidence[]
      explanation: string
    }
