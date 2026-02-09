import { useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  useExternalSessionDetail,
  useContinueExternalSession,
  useProject,
} from '../hooks/useProjects'
import MessageList from '../components/sessions/MessageList'
import PromptInput from '../components/sessions/PromptInput'
import Button from '../components/common/Button'
import type { Message } from '../api/types'

function formatModel(model: string | null): string {
  if (!model) return 'Unknown'
  const match = model.match(/claude-(\w+)-([\d-]+)/)
  if (!match) return model
  const name = match[1].charAt(0).toUpperCase() + match[1].slice(1)
  const parts = match[2].split('-')
  const version = parts.length >= 2 ? `${parts[0]}.${parts[1]}` : parts[0]
  return `${name} ${version}`
}

function formatTimestamp(ts: string | null): string {
  if (!ts) return '--'
  const d = new Date(ts)
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function ExternalSessionPage() {
  const { projectId, sessionId } = useParams<{
    projectId: string
    sessionId: string
  }>()
  const navigate = useNavigate()
  const { data: detail, isLoading, error } = useExternalSessionDetail(
    projectId!,
    sessionId!,
  )
  const { data: project } = useProject(projectId!)
  const continueMutation = useContinueExternalSession()
  const [continued, setContinued] = useState(false)

  const handleContinue = useCallback(
    (prompt: string) => {
      if (!projectId || !sessionId || continued) return
      setContinued(true)
      continueMutation.mutate(
        {
          projectId,
          sessionId,
          data: {
            prompt,
            name: detail?.slug
              ? `Continued: ${detail.slug}`
              : undefined,
          },
        },
        {
          onSuccess: (newSession) => {
            navigate(`/sessions/${newSession.id}`)
          },
          onError: () => {
            setContinued(false)
          },
        },
      )
    },
    [projectId, sessionId, detail?.slug, continued, continueMutation, navigate],
  )

  const goBack = useCallback(() => {
    navigate(projectId ? `/projects/${projectId}` : '/')
  }, [navigate, projectId])

  // ── Loading ───────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-zurk-900">
        <div className="flex flex-col items-center gap-3">
          <div className="w-6 h-6 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-zurk-400">Loading session history...</p>
        </div>
      </div>
    )
  }

  // ── Error / Not Found ─────────────────────────────────────────────
  if (error || !detail) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-zurk-900">
        <div className="text-center space-y-3">
          <p className="text-sm text-status-error">
            {error ? String(error) : 'Session not found'}
          </p>
          <Button variant="ghost" size="sm" onClick={goBack}>
            Back to Project
          </Button>
        </div>
      </div>
    )
  }

  // ExternalMessage is structurally identical to Message — safe to cast
  const messages = detail.messages as unknown as Message[]

  // Use slug, or first user message as title, or session ID prefix
  const firstUserMsg = messages.find((m) => m.role === 'user')
  const sessionTitle = detail.slug
    ?? firstUserMsg?.content.slice(0, 80)
    ?? detail.session_id.slice(0, 8)

  return (
    <div className="fixed inset-0 flex flex-col bg-zurk-900">
      {/* ── Header (pinned) ──────────────────────────────────────────── */}
      <div className="shrink-0 border-b border-zurk-700/70 bg-zurk-800/60 backdrop-blur-md">
        <div className="flex items-center gap-3 px-4 sm:px-5 py-3">
          {/* Back button */}
          <button
            onClick={goBack}
            className="shrink-0 p-1.5 -ml-1 rounded-md text-white hover:bg-zurk-700/50 transition-colors"
            aria-label="Go back"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
            </svg>
          </button>

          {/* Title + project + metadata stacked */}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-white truncate leading-tight" title={sessionTitle}>
              {sessionTitle}
            </p>
            <div className="flex items-center gap-2 mt-0.5">
              {project && (
                <span className="text-[11px] text-zurk-300 truncate">{project.name}</span>
              )}
              {project && <span className="text-zurk-600 text-[10px]">/</span>}
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-zurk-700 text-zurk-300 shrink-0">
                External
              </span>
            </div>
          </div>

          {/* Right: stats */}
          <div className="flex items-center gap-3 text-xs text-zurk-400 shrink-0">
            <span className="hidden sm:inline">{formatModel(detail.model)}</span>
            <span>{detail.total_messages} msgs</span>
            {detail.started_at && (
              <span className="hidden sm:inline text-zurk-500">{formatTimestamp(detail.started_at)}</span>
            )}
          </div>
        </div>
      </div>

      {/* ── Messages (only this scrolls) ─────────────────────────────── */}
      <div className="flex-1 min-h-0">
        <MessageList messages={messages} scrollToBottomOnMount />
      </div>

      {/* ── Continue prompt (pinned at bottom) ───────────────────────── */}
      <div className="shrink-0">
        <PromptInput
          onSend={handleContinue}
          disabled={continued}
          loading={continueMutation.isPending}
          placeholder="Continue session..."
        />
      </div>
    </div>
  )
}
