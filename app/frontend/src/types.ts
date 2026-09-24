export type Confidence = 'confirmed' | 'probable' | 'possible' | 'weak' | 'false_positive'
export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'informational'
export type ScanStatus = 'pending' | 'running' | 'completed' | 'failed' | 'interrupted'
export type ActionStatus = 'pending' | 'approved' | 'declined' | 'completed' | 'expired'
export type ExecutionStatus = 'pending' | 'submitted' | 'verifying' | 'removed' | 'still_present' | 'requires_manual' | 'failed'

export interface Scan {
  id: number
  targetType: string
  targetValue: string
  scanMode: 'local' | 'hybrid'
  status: ScanStatus
  createdAt: string
  startedAt: string | null
  completedAt: string | null
  coverage: Record<string, unknown> | null
  error: string | null
}

export interface Finding {
  id: number
  scanId: number
  type: string
  title: string
  source: string
  url: string | null
  evidence: string | null
  confidence: Confidence
  severity: Severity
  timestamp: string
  scope: string | null
  tool: string | null
  status: string
  actionId: number | null
}

export interface ExecutionSummary {
  attempt: number | null
  status: ExecutionStatus | null
  channel: string | null
  targetUrl: string | null
  verifiedAt: string | null
  verificationDetail: string | null
  note: string | null
}

export interface SiteAdvisory {
  category: string
  recommended: boolean | null
  rationale: string
}

export interface ToolRun {
  id: number
  scanId: number | null
  tool: string
  status: string
  durationMs: number
  coverage: string | null
  findingsCount: number
  errors: string[] | null
  rawReference: string | null
  startedAt: string
  completedAt: string | null
}

export interface GraphNode {
  id: number
  kind: string
  value: string
  canonical: string
  scanCount: number
  evidenceCount: number
}

export interface GraphEdge {
  source: number
  target: number
  type: string
  evidenceFindingId: number | null
}

export interface Graph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface ImageDetails {
  id: number
  scanId: number | null
  filename: string
  localPath: string
  md5: string | null
  sha256: string | null
  phash: string | null
  exif: Record<string, unknown> | null
  createdAt: string
}

export interface RiskBreakdown {
  severity: number
  confidence: number
  sourceReliability: number
  sensitivity: number
  exposureAge: number
  correlation: number
  score: number
  riskScore: number
  level: string
  gated: boolean
  extra: Record<string, unknown>
}

export interface FindingRisk {
  findingId: number
  type: string
  title: string
  score: number
  riskScore: number
  level: string
  breakdown: RiskBreakdown
}

export interface ScanRisk {
  scanId: number
  riskScore: number
  level: string
  averageRiskScore: number
  findingCount: number
  findings: FindingRisk[]
}

export interface PrivacyAction {
  id: number
  findingId: number | null
  recommendedAction: string
  deletionUrl: string | null
  instructions: string | null
  evidenceReference: string | null
  approvalRequired: boolean
  status: ActionStatus
  createdAt: string
  approvedAt: string | null
  siteAdvisory: SiteAdvisory | null
  execution: ExecutionSummary | null
}

export interface RemovalResult {
  findingId: number
  actionId: number
  status: string
  execution: ExecutionSummary | null
}

export interface WorkerStatus {
  mode: string
  localAiConfigured: boolean
  localAiAvailable: boolean
  colabAiConfigured: boolean
  colabAiAvailable: boolean
  colabDispatcherConfigured: boolean
  colabApprovalRequired: boolean
}

export interface LogEntry {
  id: number
  timestamp: string
  actor: string
  action: string
  entityType: string
  entityId: number | null
  detail: string | null
}

export interface Settings {
  readOnly: boolean
  osintEnabled: boolean
  defaultScanMode: string
  hybridRequiresExplicitApproval: boolean
  localAiConfigured: boolean
  localAiAvailable: boolean
  colabAiConfigured: boolean
  colabAiAvailable: boolean
  colabDispatcherConfigured: boolean
  colabApprovalRequired: boolean
  uploadMaxBytes: number
}

export interface Paginated<T> {
  data: T[]
  pagination: { page: number; pageSize: number; totalItems: number; totalPages: number }
}

export interface Report {
  scan: Scan
  totalFindings: number
  bySeverity: Record<string, number>
  byConfidence: Record<string, number>
  toolsRun: number
  sourcesChecked: string[]
  aiAvailable: boolean
}

export type AgentStepKind =
  | 'user'
  | 'start'
  | 'done'
  | 'thought'
  | 'tool'
  | 'result'
  | 'evidence'
  | 'error'
  | 'confirm'

export interface AgentStep {
  kind: AgentStepKind
  label: string
  detail: string
  evidence: string[]
  data: Record<string, unknown>
}

export interface AgentStreamEvent extends AgentStep {
  conversationId?: number
  message?: string
  answer?: string
  blocked?: boolean
}

export interface AgentDone {
  conversationId: number
  answer: string
  blocked: boolean
  confirmRequired: string[]
}

export interface AgentStatus {
  enabled: boolean
  configured: boolean
  backend: string
}

export interface AgentConversation {
  id: number
  title: string
  status: string
  hybridApproved: boolean
  createdAt: string
  updatedAt: string
}

export interface AgentMessage {
  id: number
  role: string
  content: string | null
  blocked: boolean
  steps: AgentStep[] | null
  answer: string | null
  createdAt: string
}

export interface AgentConversationDetail extends AgentConversation {
  messages: AgentMessage[]
}