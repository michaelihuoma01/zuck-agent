/**
 * ZURK API client — typed fetch wrapper for all backend endpoints.
 *
 * In dev mode, Vite proxies /api/* → http://localhost:8000/*
 * In production, set VITE_API_BASE_URL to the actual backend URL.
 */

import type {
  Project,
  ProjectCreate,
  ProjectUpdate,
  ProjectListResponse,
  PreviewStatus,
  ExternalSessionListResponse,
  ExternalSessionDetail,
  ContinueExternalSessionRequest,
  GlobalExternalSessionListResponse,
  DirectoryListResponse,
  Session,
  SessionCreate,
  SessionPrompt,
  SessionListResponse,
  SessionWithMessages,
  MessageListResponse,
  HealthResponse,
  AgentHealthResponse,
  StreamMessage,
} from './types'

// ── Configuration ───────────────────────────────────────────────────

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'
const API_KEY = import.meta.env.VITE_API_KEY ?? ''

// ── Fetch wrapper ───────────────────────────────────────────────────

class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

const REQUEST_TIMEOUT_MS = 30_000

/** User-friendly messages for common HTTP status codes */
const STATUS_MESSAGES: Record<number, string> = {
  400: 'Invalid request — please check your input',
  401: 'Authentication required',
  403: 'You don\'t have permission to do that',
  404: 'The requested resource was not found',
  409: 'Conflict — the resource was modified elsewhere',
  422: 'Validation failed — please check your input',
  429: 'Too many requests — please slow down',
  500: 'Server error — please try again later',
  502: 'Backend is unreachable',
  503: 'Service temporarily unavailable',
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
    ...(options.headers as Record<string, string> ?? {}),
  }

  // Abort controller for timeout
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  let res: Response
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers,
      signal: controller.signal,
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ApiError(408, 'Request timed out — the server took too long to respond')
    }
    throw new ApiError(0, 'Network error — check your connection and try again')
  } finally {
    clearTimeout(timeout)
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: undefined }))
    const detail = body.detail ?? STATUS_MESSAGES[res.status] ?? res.statusText
    throw new ApiError(res.status, detail)
  }

  // 204 No Content
  if (res.status === 204) return undefined as T

  return res.json()
}

// ── Health ──────────────────────────────────────────────────────────

export const health = {
  check: () => request<HealthResponse>('/health'),
  agent: () => request<AgentHealthResponse>('/health/agent'),
}

// ── Projects ────────────────────────────────────────────────────────

export const projects = {
  list: () => request<ProjectListResponse>('/projects'),

  get: (id: string) => request<Project>(`/projects/${id}`),

  create: (data: ProjectCreate) =>
    request<Project>('/projects', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: ProjectUpdate) =>
    request<Project>(`/projects/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request<void>(`/projects/${id}`, { method: 'DELETE' }),

  validate: (id: string) =>
    request<{ valid: boolean }>(`/projects/${id}/validate`),

  externalSessions: (id: string) =>
    request<ExternalSessionListResponse>(`/projects/${id}/external-sessions`),

  externalSessionDetail: (projectId: string, sessionId: string) =>
    request<ExternalSessionDetail>(
      `/projects/${projectId}/external-sessions/${sessionId}`,
    ),

  continueExternalSession: (
    projectId: string,
    sessionId: string,
    data: ContinueExternalSessionRequest,
  ) =>
    request<Session>(
      `/projects/${projectId}/external-sessions/${sessionId}/continue`,
      { method: 'POST', body: JSON.stringify(data) },
    ),

  preview: {
    start: (projectId: string) =>
      request<PreviewStatus>(`/projects/${projectId}/preview/start`, { method: 'POST', body: '{}' }),
    stop: (projectId: string) =>
      request<PreviewStatus>(`/projects/${projectId}/preview/stop`, { method: 'POST', body: '{}' }),
    status: (projectId: string) =>
      request<PreviewStatus>(`/projects/${projectId}/preview/status`),
  },
}

// ── Sessions ────────────────────────────────────────────────────────

export const sessions = {
  list: (params?: { project_id?: string; status?: string }) => {
    const query = new URLSearchParams()
    if (params?.project_id) query.set('project_id', params.project_id)
    if (params?.status) query.set('session_status', params.status)
    const qs = query.toString()
    return request<SessionListResponse>(`/sessions${qs ? `?${qs}` : ''}`)
  },

  allExternal: (limit = 50) =>
    request<GlobalExternalSessionListResponse>(
      `/sessions/external?limit=${limit}`,
    ),

  get: (id: string) =>
    request<SessionWithMessages>(`/sessions/${id}`),

  create: (data: SessionCreate) =>
    request<Session>('/sessions', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  sendPrompt: (id: string, data: SessionPrompt) =>
    request<Session>(`/sessions/${id}/prompt`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request<void>(`/sessions/${id}`, { method: 'DELETE' }),

  messages: (id: string, params?: { limit?: number; since?: string }) => {
    const query = new URLSearchParams()
    if (params?.limit) query.set('limit', String(params.limit))
    if (params?.since) query.set('since', params.since)
    const qs = query.toString()
    return request<MessageListResponse>(
      `/sessions/${id}/messages${qs ? `?${qs}` : ''}`,
    )
  },

  approve: (id: string, feedback?: string) =>
    request<{ status: string }>(`/sessions/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approved: true, feedback: feedback ?? null }),
    }),

  deny: (id: string, feedback?: string) =>
    request<{ status: string }>(`/sessions/${id}/deny`, {
      method: 'POST',
      body: JSON.stringify({ approved: false, feedback: feedback ?? null }),
    }),

  cancel: (id: string) =>
    request<{ status: string }>(`/sessions/${id}/cancel`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),
}

// ── Filesystem ──────────────────────────────────────────────────────

export const filesystem = {
  browse: (path?: string) => {
    const query = path ? `?path=${encodeURIComponent(path)}` : ''
    return request<DirectoryListResponse>(`/filesystem/browse${query}`)
  },
}

// ── WebSocket ───────────────────────────────────────────────────────

export function connectWebSocket(
  sessionId: string,
  handlers: {
    onMessage: (msg: StreamMessage) => void
    onOpen?: () => void
    onClose?: () => void
    onError?: (event: Event) => void
  },
): WebSocket {
  // Build WS URL — in dev, Vite proxies /ws → ws://localhost:8000
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = import.meta.env.VITE_WS_HOST ?? window.location.host
  const apiKeyParam = API_KEY ? `?api_key=${encodeURIComponent(API_KEY)}` : ''
  const url = `${protocol}//${host}/ws/sessions/${sessionId}${apiKeyParam}`

  const ws = new WebSocket(url)

  ws.onopen = () => handlers.onOpen?.()

  ws.onmessage = (event) => {
    try {
      const msg: StreamMessage = JSON.parse(event.data)
      handlers.onMessage(msg)
    } catch {
      // Ignore malformed messages
    }
  }

  ws.onclose = () => handlers.onClose?.()
  ws.onerror = (event) => handlers.onError?.(event)

  return ws
}

// ── SSE (mobile fallback) ───────────────────────────────────────────

export function connectSSE(
  sessionId: string,
  onMessage: (msg: StreamMessage) => void,
): EventSource {
  const url = `${BASE_URL}/sessions/${sessionId}/stream`
  const source = new EventSource(url)

  source.onmessage = (event) => {
    try {
      const msg: StreamMessage = JSON.parse(event.data)
      onMessage(msg)
    } catch {
      // Ignore malformed messages
    }
  }

  return source
}

export { ApiError }
