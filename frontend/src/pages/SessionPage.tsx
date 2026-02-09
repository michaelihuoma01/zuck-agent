import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  useSession,
  useSendPrompt,
  useApproveSession,
  useDenySession,
  useCancelSession,
} from '../hooks/useSessions'
import { useProject } from '../hooks/useProjects'
import { useWebSocket } from '../hooks/useWebSocket'
import MessageList from '../components/sessions/MessageList'
import PromptInput from '../components/sessions/PromptInput'
import ApprovalBanner from '../components/approval/ApprovalBanner'
import { StatusPill, StatsPopover } from '../components/sessions/SessionStatus'
import Button from '../components/common/Button'
import PreviewButton from '../components/common/PreviewButton'
import { useToast } from '../components/common/Toast'

export default function SessionPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: session, isLoading } = useSession(id!)
  const { data: project } = useProject(session?.project_id ?? '')
  const sendPrompt = useSendPrompt()
  const approve = useApproveSession()
  const deny = useDenySession()
  const cancel = useCancelSession()
  const { success, error: showError } = useToast()

  // WebSocket: only connect for active sessions
  const isActive = session?.status === 'running' || session?.status === 'waiting_approval'
  const { connectionState, transport } = useWebSocket({
    sessionId: id!,
    enabled: !!session && isActive,
  })

  const handleSend = useCallback(
    (prompt: string) => {
      sendPrompt.mutate({ id: id!, prompt })
    },
    [id, sendPrompt],
  )

  const handleRetry = useCallback(() => {
    if (!session || sendPrompt.isPending) return
    const hasWork = (session.messages ?? []).some(
      (m) => m.role === 'assistant',
    )
    const prompt = hasWork
      ? 'Continue from where you left off.'
      : session.last_prompt
    if (!prompt) return
    setErrorDismissed(true)
    sendPrompt.mutate({ id: id!, prompt })
  }, [id, session, sendPrompt])

  const handleCancel = useCallback(() => {
    cancel.mutate(id!, {
      onSuccess: () => success('Session cancelled'),
      onError: (err) => showError(err instanceof Error ? err.message : 'Failed to cancel'),
    })
  }, [id, cancel, success, showError])

  const [errorDismissed, setErrorDismissed] = useState(false)
  const prevErrorMsg = useRef(session?.error_message)
  useEffect(() => {
    if (session?.error_message && session.error_message !== prevErrorMsg.current) {
      setErrorDismissed(false)
    }
    prevErrorMsg.current = session?.error_message ?? null
  }, [session?.error_message])

  // ── Loading / Not Found ─────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-zurk-900">
        <div className="flex flex-col items-center gap-3">
          <div className="w-6 h-6 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-zurk-400">Loading session...</p>
        </div>
      </div>
    )
  }

  if (!session) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-zurk-900">
        <div className="text-center space-y-3">
          <p className="text-sm text-status-error">Session not found</p>
          <Button variant="ghost" size="sm" onClick={() => navigate('/')}>
            Back to Dashboard
          </Button>
        </div>
      </div>
    )
  }

  // ── Derived state ───────────────────────────────────────────────

  const messages = session.messages ?? []
  const isRunning = session.status === 'running'
  const isWaiting = session.status === 'waiting_approval'
  const isCompleted = session.status === 'completed'
  const isError = session.status === 'error'
  const isIdle = session.status === 'idle'
  const hasAssistantMessages = messages.some((m) => m.role === 'assistant')

  const canSendPrompt = (isIdle || isCompleted || isError) && !sendPrompt.isPending

  const sessionTitle = session.name ?? session.last_prompt?.slice(0, 50) ?? 'Session'

  return (
    <div className="fixed inset-0 flex flex-col bg-zurk-900">
      {/* ── Header (pinned) ────────────────────────────────────────── */}
      <div className="shrink-0 border-b border-zurk-700/70 bg-zurk-800/60 backdrop-blur-md">
        <div className="flex items-center gap-3 px-4 sm:px-5 py-3">
          {/* Back button — white */}
          <button
            onClick={() => project ? navigate(`/projects/${project.id}`) : navigate('/')}
            className="shrink-0 p-1.5 -ml-1 rounded-md text-white hover:bg-zurk-700/50 transition-colors"
            aria-label="Go back"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
            </svg>
          </button>

          {/* Z icon */}
          <div className="shrink-0 w-9 h-9 rounded-lg bg-zurk-700 border border-zurk-600 flex items-center justify-center">
            <span className="text-zurk-100 font-semibold text-sm leading-none">Z</span>
          </div>

          {/* Title + project + status stacked */}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-white truncate leading-tight">{sessionTitle}</p>
            <div className="flex items-center gap-2 mt-0.5">
              {project && (
                <span className="text-[11px] text-zurk-300 truncate">{project.name}</span>
              )}
              {project && <span className="text-zurk-600 text-[10px]">/</span>}
              <StatusPill session={session} />
            </div>
          </div>

          {/* Right: cancel + info */}
          <div className="flex items-center gap-2 shrink-0">
            {(isRunning || isWaiting) && (
              <Button
                variant="danger"
                size="sm"
                onClick={handleCancel}
                loading={cancel.isPending}
              >
                Cancel
              </Button>
            )}

            <StatsPopover
              session={session}
              connectionState={isActive ? connectionState : undefined}
              transport={isActive ? transport : undefined}
            />
          </div>
        </div>
      </div>

      {/* ── Preview bar (own row below header) ─────────────────────── */}
      {project?.dev_command && (
        <div className="shrink-0 border-b border-zurk-700/50 bg-zurk-800/40 px-4 sm:px-5 py-1.5">
          <PreviewButton
            projectId={session.project_id}
            devCommand={project.dev_command}
            size="sm"
          />
        </div>
      )}

      {/* ── Messages (only this scrolls) ───────────────────────────── */}
      <div className="flex-1 min-h-0">
        <MessageList messages={messages} isThinking={isRunning} />
      </div>

      {/* ── Approval Banner ────────────────────────────────────────── */}
      {isWaiting && session.pending_approval && (
        <div className="shrink-0">
          <ApprovalBanner
            approval={session.pending_approval}
            onApprove={(feedback) =>
              approve.mutate({ id: session.id, feedback }, {
                onSuccess: () => success('Approved'),
                onError: (err) => showError(err instanceof Error ? err.message : 'Approval failed'),
              })
            }
            onDeny={(feedback) =>
              deny.mutate({ id: session.id, feedback }, {
                onSuccess: () => success('Denied'),
                onError: (err) => showError(err instanceof Error ? err.message : 'Denial failed'),
              })
            }
            loading={approve.isPending || deny.isPending}
          />
        </div>
      )}

      {/* ── Error Banner ───────────────────────────────────────────── */}
      {isError && !errorDismissed && (
        <div className="shrink-0 mx-5 mb-2 animate-[fadeSlideUp_0.25s_ease-out]">
          <div className="bg-status-error/5 border border-status-error/20 rounded-lg px-4 py-2.5">
            <div className="flex items-start gap-3">
              <span className="text-status-error text-sm mt-0.5">✕</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-status-error font-medium">Session Error</p>
                {session.error_message && (
                  <p className="text-xs text-zurk-300 mt-1 break-words">
                    {session.error_message}
                  </p>
                )}
              </div>
              {(session.last_prompt || hasAssistantMessages) && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleRetry}
                  disabled={sendPrompt.isPending}
                  loading={sendPrompt.isPending}
                >
                  {hasAssistantMessages ? 'Continue' : 'Retry'}
                </Button>
              )}
              <button
                onClick={() => setErrorDismissed(true)}
                className="shrink-0 text-zurk-400 hover:text-zurk-200 transition-colors p-0.5"
                aria-label="Dismiss error"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Input (pinned at bottom) ───────────────────────────────── */}
      <div className="shrink-0">
        <PromptInput
          onSend={handleSend}
          disabled={!canSendPrompt}
          loading={sendPrompt.isPending}
          placeholder={
            isRunning
              ? 'Claude is working...'
              : isWaiting
                ? 'Waiting for approval...'
                : isError
                  ? 'Send a new prompt or retry above...'
                  : 'Send a message...'
          }
        />
      </div>
    </div>
  )
}
