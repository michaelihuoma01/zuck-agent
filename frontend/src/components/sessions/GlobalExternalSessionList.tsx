import { Link } from 'react-router-dom'
import type { GlobalExternalSession } from '../../api/types'

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const minutes = Math.floor(diff / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function formatModel(model: string | null): string {
  if (!model) return 'Unknown'
  const match = model.match(/claude-(\w+)-([\d-]+)/)
  if (!match) return model
  const name = match[1].charAt(0).toUpperCase() + match[1].slice(1)
  const parts = match[2].split('-')
  const version = parts.length >= 2 ? `${parts[0]}.${parts[1]}` : parts[0]
  return `${name} ${version}`
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const kb = bytes / 1024
  if (kb < 1024) return `${kb.toFixed(0)} KB`
  const mb = kb / 1024
  return `${mb.toFixed(1)} MB`
}

function sessionTitle(session: GlobalExternalSession): string {
  if (session.title) return session.title
  return session.slug ?? session.session_id.slice(0, 8)
}

interface GlobalExternalSessionListProps {
  sessions: GlobalExternalSession[]
}

export default function GlobalExternalSessionList({ sessions }: GlobalExternalSessionListProps) {
  if (sessions.length === 0) {
    return (
      <div className="text-center py-10">
        <p className="text-zurk-400 text-sm">No external sessions found</p>
        <p className="text-zurk-500 text-xs mt-1">
          Sessions started from VS Code or CLI will appear here
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-1">
      {sessions.map((session) => (
        <Link
          key={`${session.project_id}-${session.session_id}`}
          to={`/projects/${session.project_id}/external-sessions/${session.session_id}`}
          className="flex items-center gap-3 px-4 py-3 rounded-lg hover:bg-zurk-700/50 transition-colors cursor-pointer"
        >
          {/* Terminal icon */}
          <div className="shrink-0 w-8 h-8 rounded-lg bg-zurk-700 flex items-center justify-center">
            <svg className="w-4 h-4 text-zurk-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="m6.75 7.5 3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0 0 21 18V6a2.25 2.25 0 0 0-2.25-2.25H5.25A2.25 2.25 0 0 0 3 6v12a2.25 2.25 0 0 0 2.25 2.25Z" />
            </svg>
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-medium text-zurk-100 truncate" title={sessionTitle(session)}>
                {sessionTitle(session)}
              </span>
            </div>
            <div className="flex items-center gap-2 mt-0.5 flex-wrap">
              {/* Time ago */}
              <span className="text-xs text-zurk-400">
                {session.started_at ? timeAgo(session.started_at) : '—'}
              </span>
              <span className="text-zurk-600">&middot;</span>
              {/* Git branch pill */}
              {session.git_branch && (
                <span className="text-xs text-emerald-400">
                  {session.git_branch}
                </span>
              )}
              {session.git_branch && <span className="text-zurk-600">&middot;</span>}
              {/* File size */}
              <span className="text-xs text-zurk-500">
                {formatBytes(session.file_size_bytes)}
              </span>
            </div>
          </div>

          {/* Right side: project + model badges */}
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-accent-500/10 text-accent-400">
              {session.project_name}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-zurk-600 text-zurk-300 hidden sm:inline">
              {formatModel(session.model)}
            </span>
          </div>

        </Link>
      ))}
    </div>
  )
}
