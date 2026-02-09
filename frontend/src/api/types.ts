/** API types mirroring backend Pydantic schemas (src/api/schemas.py) */

// ── Projects ────────────────────────────────────────────────────────

export interface Project {
  id: string
  name: string
  path: string
  description: string | null
  default_allowed_tools: string[] | null
  permission_mode: string
  auto_approve_patterns: string[] | null
  dev_command: string | null
  dev_port: number | null
  created_at: string
  updated_at: string
}

export interface ProjectCreate {
  name: string
  path: string
  description?: string | null
  default_allowed_tools?: string[] | null
  permission_mode?: string
  auto_approve_patterns?: string[] | null
  validate_path?: boolean
  dev_command?: string | null
  dev_port?: number | null
}

export interface ProjectUpdate {
  name?: string | null
  description?: string | null
  default_allowed_tools?: string[] | null
  permission_mode?: string | null
  auto_approve_patterns?: string[] | null
  dev_command?: string | null
  dev_port?: number | null
}

export interface ProjectListResponse {
  projects: Project[]
  total: number
}

export interface PreviewStatus {
  running: boolean
  url: string | null
  port: number | null
  pid: number | null
  uptime_seconds: number | null
  project_type: string | null
  error: string | null
}

// ── Sessions ────────────────────────────────────────────────────────

export type SessionStatus =
  | 'idle'
  | 'running'
  | 'completed'
  | 'error'
  | 'waiting_approval'

export interface PendingApproval {
  tool_name: string
  tool_input: Record<string, unknown>
  tool_use_id: string
  diff?: string
  diff_stats?: { additions: number; deletions: number; files_changed: number }
  risk_level?: 'high' | 'medium' | 'low'
  diff_tier?: 'inline' | 'truncated'
  total_bytes?: number
  total_lines?: number
}

export interface Session {
  id: string
  claude_session_id: string | null
  project_id: string
  name: string | null
  status: SessionStatus
  last_prompt: string | null
  pending_approval: PendingApproval | null
  message_count: number
  total_cost_usd: number
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface SessionCreate {
  project_id: string
  prompt: string
  name?: string | null
}

export interface SessionPrompt {
  prompt: string
}

export interface SessionListResponse {
  sessions: Session[]
  total: number
}

// ── Messages ────────────────────────────────────────────────────────

export interface Message {
  id: string
  session_id: string
  role: string
  content: string
  message_type: string | null
  metadata: Record<string, unknown> | null
  timestamp: string
}

export interface SessionWithMessages extends Session {
  messages: Message[]
}

export interface MessageListResponse {
  messages: Message[]
  total: number
}

// ── Stream (discriminated union matching backend MessageType enum) ───

/** All possible `type` values from the backend WebSocket. */
export type StreamMessageType =
  | 'init'
  | 'text'
  | 'tool_use'
  | 'tool_result'
  | 'result'
  | 'error'
  | 'user'
  | 'status'
  | 'history'
  | 'pong'
  | 'approval_required'
  | 'approval_processed'

interface StreamBase {
  timestamp?: string | null
}

export interface StreamInit extends StreamBase {
  type: 'init'
  session_id: string
}

export interface StreamText extends StreamBase {
  type: 'text'
  content: string
}

export interface StreamToolUse extends StreamBase {
  type: 'tool_use'
  tool_name: string
  tool_input: Record<string, unknown>
  tool_use_id: string
}

export interface StreamToolResult extends StreamBase {
  type: 'tool_result'
  tool_result: string
  tool_use_id?: string
  is_error?: boolean
}

export interface StreamResult extends StreamBase {
  type: 'result'
  total_cost_usd?: number
  duration_ms?: number
  session_id?: string
  is_complete?: boolean
}

export interface StreamError extends StreamBase {
  type: 'error'
  content: string
}

export interface StreamUser extends StreamBase {
  type: 'user'
  content: string
}

export interface StreamStatus extends StreamBase {
  type: 'status'
  status: string
  session_id?: string
}

export interface StreamHistoryMessage {
  role: string
  content: string
  timestamp?: string | null
}

export interface StreamHistory extends StreamBase {
  type: 'history'
  messages: StreamHistoryMessage[]
}

export interface StreamPong extends StreamBase {
  type: 'pong'
}

export interface StreamApprovalRequired extends StreamBase {
  type: 'approval_required'
  tool_name: string
  tool_input: Record<string, unknown>
  tool_use_id: string
  diff?: string
  diff_stats?: { additions: number; deletions: number; files_changed: number }
  risk_level?: 'high' | 'medium' | 'low'
  session_id?: string
}

export interface StreamApprovalProcessed extends StreamBase {
  type: 'approval_processed'
  approved: boolean
  session_id?: string
}

/** Discriminated union of all WebSocket message shapes. */
export type StreamMessage =
  | StreamInit
  | StreamText
  | StreamToolUse
  | StreamToolResult
  | StreamResult
  | StreamError
  | StreamUser
  | StreamStatus
  | StreamHistory
  | StreamPong
  | StreamApprovalRequired
  | StreamApprovalProcessed

// ── External Sessions (Claude Code session discovery) ────────────────

export interface ExternalSession {
  session_id: string
  file_path: string
  file_size_bytes: number
  slug: string | null
  started_at: string | null
  ended_at: string | null
  model: string | null
  claude_code_version: string | null
  total_entries: number
  user_messages: number
  assistant_messages: number
  has_subagents: boolean
  cwd: string | null
  git_branch: string | null
  title: string | null
}

export interface ExternalSessionListResponse {
  sessions: ExternalSession[]
  total: number
  project_path: string
  claude_dir: string
}

export interface GlobalExternalSession extends ExternalSession {
  project_id: string
  project_name: string
}

export interface GlobalExternalSessionListResponse {
  sessions: GlobalExternalSession[]
  total: number
}

// ── External Session Detail (full conversation view) ─────────────────

export interface ExternalMessage {
  id: string
  session_id: string
  role: string
  content: string
  message_type: string | null
  metadata: Record<string, unknown> | null
  timestamp: string
}

export interface ExternalSessionDetail {
  session_id: string
  slug: string | null
  model: string | null
  claude_code_version: string | null
  started_at: string | null
  ended_at: string | null
  messages: ExternalMessage[]
  total_messages: number
}

export interface ContinueExternalSessionRequest {
  prompt: string
  name?: string | null
}

// ── Filesystem Browser (folder picker) ──────────────────────────────

export interface DirectoryEntry {
  name: string
  path: string
  has_children: boolean
  project_indicators: string[]
}

export interface BreadcrumbEntry {
  name: string
  path: string
}

export interface DirectoryListResponse {
  current_path: string
  entries: DirectoryEntry[]
  shortcuts: DirectoryEntry[]
  breadcrumbs: BreadcrumbEntry[]
  parent_path: string | null
}

// ── Health ───────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string
  version: string
}

export interface AgentHealthResponse {
  status: string
  cli_available: boolean
  error?: string | null
}
