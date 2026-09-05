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
  root_address_id: number
  /** So a screen can name the address being analysed without a second request. */
  root_address: string | null
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

// --- analysis results (API_SPEC §6) ------------------------------------------
// The shapes the pipeline now actually produces. Raw amounts cross the wire as
// strings: a JSON number cannot hold an 18-decimal amount exactly, and an amount
// that loses precision in transport is a wrong number in a police report.

export interface GraphNode {
  address: string
  depth: number | null
  taint_share: number | null
  tainted_amount_raw: string
  is_root: boolean
  is_terminal: boolean
  termination_reason: string | null
  attribution_tier: AttributionTier | null
  entity_name: string | null
  entity_type: EntityType | null
  attribution_confidence: number | null
  first_reached_at: string | null
  omitted_successors: number
  pruned_branches: { to: string; reason: string; tainted_amount_raw: string }[]
}

export interface GraphEdge {
  from: string
  to: string
  asset_symbol: string | null
  decimals: number | null
  total_amount_raw: string
  tainted_amount_raw: string
  transfer_count: number
  first_transfer_at: string | null
  last_transfer_at: string | null
  tx_hashes: string[]
}

export interface GraphMeasures {
  chokepoints: { address: string; betweenness: number }[]
  components: number
  cycles: string[][]
  highest_value_path: string[]
}

export interface GraphPayload {
  root: string | null
  anchor_tx_hash: string | null
  asset_key: string | null
  node_count: number
  edge_count: number
  total_nodes: number
  /** Always present, and always displayed. Hiding half a fund flow is unacceptable. */
  truncated: boolean
  omitted_node_count: number
  nodes: GraphNode[]
  edges: GraphEdge[]
  measures: GraphMeasures
  pruned_branches: { from: string; to: string; reason: string; tainted_amount_raw: string }[]
  unavailable_addresses: { address: string; reason: string }[]
}

export interface AttributionRow {
  address: string
  tier: AttributionTier
  entity_name: string | null
  entity_type: EntityType
  /** Null for CONFIRMED: a confirmed claim is not a probability. */
  confidence: number | null
  method: AttributionMethod
  evidence: { type?: string; detail?: unknown; [key: string]: unknown }[]
  engine_version: string
  computed_at: string
}

export interface PatternRow {
  pattern_type: string
  severity: 'LOW' | 'MEDIUM' | 'HIGH'
  subject_address: string
  involved_addresses: string[]
  trigger_tx_hashes: string[]
  metrics: Record<string, unknown>
  explanation: string
  /** Mandatory. A pattern shown without it will be read as a conclusion. */
  false_positive_note: string
  detector_version: string
}

export interface RiskSignal {
  name: string
  weight: number
  points: number
  raw_value: unknown
  description: string
  evidence_tx: string[]
}

export interface RiskRow {
  address: string
  score: number
  band: RiskBand
  /** Reported beside the score, never folded into it. */
  confidence: number
  signals: RiskSignal[]
  not_evaluated: { name: string; reason: string }[]
  config_version: string
  engine_version: string
  computed_at: string
}

export interface RiskPayload {
  root: RiskRow | null
  nodes: RiskRow[]
  disclaimer: string
}

export interface ReportRow {
  id: string
  case_id: string
  analysis_run_id: string | null
  report_type: 'FULL' | 'SUMMARY'
  format: 'PDF' | 'JSON' | 'CSV'
  content_sha256: string
  narrative_source: 'TEMPLATE' | 'LLM'
  generated_by: number
  generated_at: string
  download_url: string
  content_verified: boolean | null
}
