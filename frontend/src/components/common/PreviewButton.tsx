import { useState } from 'react'
import { usePreview } from '../../hooks/usePreview'

interface PreviewButtonProps {
  projectId: string
  devCommand: string | null
  size?: 'sm' | 'md'
}

export default function PreviewButton({
  projectId,
  devCommand,
  size = 'md',
}: PreviewButtonProps) {
  const { status, start, stop } = usePreview(projectId)
  const [errorDismissed, setErrorDismissed] = useState(false)

  if (!devCommand) return null

  const isStarting = start.isPending
  const isStopping = stop.isPending

  const mutationError = start.error ?? stop.error
  const statusError = status?.error
  const errorText =
    statusError ??
    (mutationError instanceof Error
      ? mutationError.message
      : mutationError
        ? String(mutationError)
        : null)
  const showError = !!(errorText && !errorDismissed && !status?.running)

  const handleStart = () => {
    setErrorDismissed(false)
    start.mutate()
  }

  const isSmall = size === 'sm'

  // ── Running ────────────────────────────────────────────────────
  if (status?.running) {
    const previewUrl = status.url ?? `http://localhost:${status.port}`
    const btnText = isSmall ? 'text-[11px]' : 'text-xs'

    return (
      <div className="flex items-center gap-2">
        <button
          onClick={() => window.open(previewUrl, '_blank', 'noopener,noreferrer')}
          className={`inline-flex items-center gap-1.5 font-medium rounded-md
            px-2.5 py-1.5 min-h-[32px] transition-colors
            bg-status-running/10 border border-status-running/25 text-status-running
            hover:bg-status-running/20 hover:border-status-running/40
            active:bg-status-running/25 ${btnText}`}
        >
          Open
          <ExternalLinkIcon />
        </button>
        <button
          onClick={() => stop.mutate()}
          disabled={isStopping}
          className={`inline-flex items-center gap-1.5 font-medium rounded-md
            px-2.5 py-1.5 min-h-[32px] transition-colors
            bg-status-error/10 border border-status-error/25 text-status-error
            hover:bg-status-error/20 hover:border-status-error/40
            active:bg-status-error/25
            disabled:opacity-40 disabled:cursor-not-allowed ${btnText}`}
        >
          {isStopping ? <SpinnerIcon /> : <StopIcon />}
          {isStopping ? 'Stopping' : 'Stop'}
        </button>
      </div>
    )
  }

  // ── Stopped / Loading ──────────────────────────────────────────
  return (
    <div className="space-y-2">
      <button
        onClick={handleStart}
        disabled={isStarting}
        className={`inline-flex items-center gap-2 font-medium text-zurk-400
          hover:text-zurk-200 active:opacity-70 disabled:opacity-50 transition-colors
          ${isSmall ? 'text-[11px]' : 'text-xs'}`}
      >
        {isStarting ? (
          <>
            <SpinnerIcon />
            Starting...
          </>
        ) : (
          <>
            <PlayIcon />
            Start
          </>
        )}
      </button>

      {showError && (
        <div className="flex items-start gap-2 text-[11px] text-status-error/80 leading-relaxed">
          <span className="shrink-0 mt-px">!</span>
          <p className="flex-1 break-words">{errorText}</p>
          <button
            onClick={() => setErrorDismissed(true)}
            className="shrink-0 text-zurk-500 hover:text-zurk-300 transition-colors"
            aria-label="Dismiss"
          >
            <CloseIcon />
          </button>
        </div>
      )}
    </div>
  )
}

/** Port number shown in the grid card label when running. */
export function usePreviewPort(projectId: string): number | null {
  const { status } = usePreview(projectId)
  return status?.running ? (status.port ?? null) : null
}

// ── Icons ────────────────────────────────────────────────────────

function ExternalLinkIcon() {
  return (
    <svg className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
    </svg>
  )
}

function PlayIcon() {
  return (
    <svg className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.347a1.125 1.125 0 0 1 0 1.972l-11.54 6.347a1.125 1.125 0 0 1-1.667-.986V5.653Z" />
    </svg>
  )
}

function SpinnerIcon() {
  return (
    <svg className="w-3 h-3 animate-spin shrink-0" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

function StopIcon() {
  return (
    <svg className="w-3 h-3 shrink-0" fill="currentColor" viewBox="0 0 24 24">
      <rect x="4" y="4" width="16" height="16" rx="2" />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
    </svg>
  )
}
