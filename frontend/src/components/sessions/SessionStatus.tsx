import { useState, useRef, useEffect } from 'react'
import type { Session } from '../../api/types'
import type { ConnectionState } from '../../hooks/useWebSocket'
import { STATUS_CONFIG } from '../../config/statusConfig'

interface SessionStatusProps {
  session: Session
  connectionState?: ConnectionState
  transport?: string | null
}

function formatDuration(createdAt: string, updatedAt: string): string {
  const diff = new Date(updatedAt).getTime() - new Date(createdAt).getTime()
  const secs = Math.floor(diff / 1000)
  if (secs < 60) return `${secs}s`
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m ${secs % 60}s`
  const hours = Math.floor(mins / 60)
  return `${hours}h ${mins % 60}m`
}

// ── Status Pill ──────────────────────────────────────────────────────

export function StatusPill({ session }: { session: Session }) {
  const { label, color, dotColor } = STATUS_CONFIG[session.status] ?? STATUS_CONFIG.idle
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${color}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
      {label}
    </span>
  )
}

// ── Connection Indicator ─────────────────────────────────────────────

function ConnectionIndicator({ state, transport }: { state: ConnectionState; transport: string | null }) {
  const config: Record<ConnectionState, { dot: string; label: string }> = {
    connected: { dot: 'bg-status-running', label: transport === 'sse' ? 'SSE' : 'Live' },
    connecting: { dot: 'bg-status-waiting animate-pulse', label: 'Connecting...' },
    reconnecting: { dot: 'bg-status-waiting animate-pulse', label: 'Reconnecting...' },
    'fallback-sse': { dot: 'bg-status-waiting', label: 'SSE fallback' },
    disconnected: { dot: 'bg-zurk-500', label: 'Offline' },
  }

  const c = config[state]
  return (
    <div className="flex items-center gap-1.5">
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      <span className="text-[10px] text-zurk-500">{c.label}</span>
    </div>
  )
}

// ── Stats Popover ────────────────────────────────────────────────────

export function StatsPopover({ session, connectionState, transport }: SessionStatusProps) {
  const [open, setOpen] = useState(false)
  const popoverRef = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handleClick = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  return (
    <div className="relative" ref={popoverRef}>
      <button
        onClick={() => setOpen(!open)}
        className="p-1.5 rounded-md text-zurk-400 hover:text-zurk-200 hover:bg-zurk-700/50 transition-colors"
        aria-label="Session info"
        title="Session info"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-56 bg-zurk-800 border border-zurk-700/70 rounded-lg shadow-xl z-30 py-2">
          {/* Status */}
          <div className="px-3 py-1.5 flex items-center justify-between">
            <span className="text-[10px] text-zurk-500 uppercase tracking-wider">Status</span>
            <StatusPill session={session} />
          </div>

          {/* Connection */}
          {connectionState && (
            <div className="px-3 py-1.5 flex items-center justify-between">
              <span className="text-[10px] text-zurk-500 uppercase tracking-wider">Connection</span>
              <ConnectionIndicator state={connectionState} transport={transport ?? null} />
            </div>
          )}

          <div className="border-t border-zurk-700/50 my-1" />

          {/* Messages */}
          <div className="px-3 py-1.5 flex items-center justify-between">
            <span className="text-[10px] text-zurk-500 uppercase tracking-wider">Messages</span>
            <span className="text-xs text-zurk-300 tabular-nums">{session.message_count}</span>
          </div>

          {/* Cost */}
          {session.total_cost_usd > 0 && (
            <div className="px-3 py-1.5 flex items-center justify-between">
              <span className="text-[10px] text-zurk-500 uppercase tracking-wider">Cost</span>
              <span className="text-xs text-zurk-300 tabular-nums">${session.total_cost_usd.toFixed(4)}</span>
            </div>
          )}

          {/* Duration */}
          <div className="px-3 py-1.5 flex items-center justify-between">
            <span className="text-[10px] text-zurk-500 uppercase tracking-wider">Duration</span>
            <span className="text-xs text-zurk-300 tabular-nums">
              {formatDuration(session.created_at, session.updated_at)}
            </span>
          </div>

          {/* Session ID */}
          <div className="border-t border-zurk-700/50 my-1" />
          <div className="px-3 py-1.5">
            <span className="text-[10px] text-zurk-500 uppercase tracking-wider">Session</span>
            <p className="text-[10px] text-zurk-400 font-mono mt-0.5 break-all">{session.id}</p>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Default export (backwards compat for other pages) ────────────────

export default function SessionStatus({ session, connectionState, transport }: SessionStatusProps) {
  const { label, color, dotColor } = STATUS_CONFIG[session.status] ?? STATUS_CONFIG.idle

  return (
    <div className="flex items-center gap-4 text-xs">
      <div className={`flex items-center gap-1.5 font-medium ${color}`}>
        <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
        <span>{label}</span>
      </div>

      {connectionState && (
        <>
          <span className="text-zurk-700">|</span>
          <ConnectionIndicator state={connectionState} transport={transport ?? null} />
        </>
      )}

      <span className="text-zurk-700">|</span>
      <span className="text-zurk-400 tabular-nums">{session.message_count} msgs</span>

      {session.total_cost_usd > 0 && (
        <>
          <span className="text-zurk-700">|</span>
          <span className="text-zurk-400 tabular-nums">${session.total_cost_usd.toFixed(4)}</span>
        </>
      )}

      {(session.status === 'completed' || session.status === 'error') && (
        <>
          <span className="text-zurk-700">|</span>
          <span className="text-zurk-500 tabular-nums">
            {formatDuration(session.created_at, session.updated_at)}
          </span>
        </>
      )}
    </div>
  )
}
