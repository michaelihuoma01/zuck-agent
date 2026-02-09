import { Link } from 'react-router-dom'
import type { ExternalSession } from '../../api/types'

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

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const kb = bytes / 1024
  if (kb < 1024) return `${kb.toFixed(0)} KB`
  const mb = kb / 1024
  return `${mb.toFixed(1)} MB`
}

function formatModel(model: string | null): string {
  if (!model) return 'Unknown'
  // 'claude-opus-4-6' → 'Opus 4.6', 'claude-sonnet-4-5-20250929' → 'Sonnet 4.5'
  const match = model.match(/claude-(\w+)-([\d-]+)/)
  if (!match) return model
  const name = match[1].charAt(0).toUpperCase() + match[1].slice(1)
  // Take first two numeric parts for version
  const parts = match[2].split('-')
  const version = parts.length >= 2 ? `${parts[0]}.${parts[1]}` : parts[0]
  return `${name} ${version}`
}

interface ExternalSessionListProps {
  sessions: ExternalSession[]
  claudeDir: string
  projectId: string
}

export default function ExternalSessionList({ sessions, claudeDir, projectId }: ExternalSessionListProps) {
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
    <div>
      {/* Directory hint */}
      <div className="px-4 py-2 border-b border-zurk-700/50">
        <p className="text-[10px] text-zurk-600 font-mono truncate">
          {claudeDir}
        </p>
      </div>

      <div className="space-y-1">
        {sessions.map((session) => (
          <Link
            key={session.session_id}
            to={`/projects/${projectId}/external-sessions/${session.session_id}`}
            className="flex items-center gap-3 px-4 py-3 rounded-lg hover:bg-zurk-700/50 transition-colors cursor-pointer"
          >
            {/* Icon: external session indicator */}
            <div className="shrink-0 w-8 h-8 rounded-lg bg-zurk-700 flex items-center justify-center">
              <svg className="w-4 h-4 text-zurk-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
              </svg>
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-zurk-100 truncate" title={session.title ?? session.slug ?? session.session_id}>
                  {session.title ?? session.slug ?? session.session_id.slice(0, 8)}
                </span>
              </div>
              <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                <span className="text-xs text-zurk-400">
                  {session.started_at ? timeAgo(session.started_at) : '—'}
                </span>
                <span className="text-zurk-600">&middot;</span>
                {session.git_branch && (
                  <>
                    <span className="text-xs text-emerald-400">
                      {session.git_branch}
                    </span>
                    <span className="text-zurk-600">&middot;</span>
                  </>
                )}
                <span className="text-xs text-zurk-500">
                  {formatBytes(session.file_size_bytes)}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-zurk-600 text-zurk-300">
                {formatModel(session.model)}
              </span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
