import { Link } from 'react-router-dom'
import type { Project, Session } from '../../api/types'
import StatusBadge from '../common/StatusBadge'
import EmptyState, { ChatIcon } from '../common/EmptyState'

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

export default function SessionList({
  sessions,
  projects = [],
}: {
  sessions: Session[]
  projects?: Project[]
}) {
  const projectMap = new Map(projects.map((p) => [p.id, p]))
  if (sessions.length === 0) {
    return (
      <EmptyState
        icon={<ChatIcon />}
        title="No sessions yet"
        description="Start a new session from a project page to begin working with Claude."
      />
    )
  }

  return (
    <div className="space-y-1">
      {sessions.map((session) => (
        <Link
          key={session.id}
          to={`/sessions/${session.id}`}
          className="flex items-center gap-3 px-4 py-3 rounded-lg hover:bg-zurk-700/50 transition-colors group"
        >
          <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-zurk-100 truncate">
              {session.name ?? session.last_prompt?.slice(0, 60) ?? 'Untitled'}
            </span>
            <StatusBadge status={session.status} />
          </div>
          <p className="text-xs text-zurk-400 mt-0.5 truncate">
            {projectMap.get(session.project_id)?.name && (
              <span className="text-zurk-300">
                {projectMap.get(session.project_id)?.name}
                <span className="text-zurk-600"> · </span>
              </span>
            )}
            {session.message_count} messages
            {session.total_cost_usd > 0 &&
              ` · $${session.total_cost_usd.toFixed(4)}`}
          </p>
        </div>
          <span className="text-xs text-zurk-500 shrink-0">
            {timeAgo(session.updated_at)}
          </span>
        </Link>
      ))}
    </div>
  )
}
