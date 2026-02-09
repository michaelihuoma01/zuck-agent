import { Link } from 'react-router-dom'
import { useSessions, useAllExternalSessions } from '../hooks/useSessions'
import { useProjects } from '../hooks/useProjects'
import SessionList from '../components/sessions/SessionList'
import GlobalExternalSessionList from '../components/sessions/GlobalExternalSessionList'
import { SessionListSkeleton } from '../components/common/Skeleton'
import Button from '../components/common/Button'

export default function Dashboard() {
  const { data: sessionData, isLoading: loadingSessions } = useSessions()
  const { data: projectData } = useProjects()
  const { data: externalData, isLoading: loadingExternal } = useAllExternalSessions(20)

  const sessions = sessionData?.sessions ?? []
  const projects = projectData?.projects ?? []
  const activeSessions = sessions.filter(
    (s) => s.status === 'running' || s.status === 'waiting_approval',
  )
  const recentSessions = sessions.slice(0, 20)

  return (
    <div className="space-y-8 max-w-4xl">
      {/* Heading */}
      <div>
        <p className="text-xs uppercase tracking-[0.3em] text-zurk-500">
          Command Center
        </p>
        <h1 className="text-2xl font-semibold text-zurk-50 mt-2">Dashboard</h1>
        <p className="text-sm text-zurk-400 mt-1">
          Overview of your agent sessions
        </p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <StatCard label="Total Sessions" value={sessions.length} />
        <StatCard
          label="Active Sessions"
          value={activeSessions.length}
          accent={activeSessions.length > 0}
        />
        <StatCard label="Projects" value={projects.length} />
      </div>

      {/* Active sessions (if any) */}
      {activeSessions.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-zurk-100 mb-3">
            Active Sessions
          </h2>
          <div className="bg-zurk-800/80 border border-zurk-700/70 rounded-xl">
            <SessionList sessions={activeSessions} projects={projects} />
          </div>
        </section>
      )}

      {/* Recent sessions */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-zurk-100">
            Recent Sessions
          </h2>
          {projects.length > 0 && (
            <Link to={`/projects/${projects[0].id}`}>
              <Button variant="primary" size="sm">
                New Session
              </Button>
            </Link>
          )}
        </div>
        <div className="bg-zurk-800/80 border border-zurk-700/70 rounded-xl">
          {loadingSessions ? (
            <SessionListSkeleton count={4} />
          ) : (
            <SessionList sessions={recentSessions} projects={projects} />
          )}
        </div>
      </section>

      {/* Claude Code Sessions (external, from all projects) */}
      <section>
        <h2 className="text-lg font-semibold text-zurk-100 mb-3">
          Claude Code Sessions
        </h2>
        <div className="bg-zurk-800/80 border border-zurk-700/70 rounded-xl">
          {loadingExternal ? (
            <SessionListSkeleton count={3} />
          ) : (
            <GlobalExternalSessionList
              sessions={externalData?.sessions ?? []}
            />
          )}
        </div>
      </section>
    </div>
  )
}

function StatCard({
  label,
  value,
  accent = false,
}: {
  label: string
  value: number
  accent?: boolean
}) {
  return (
    <div className="bg-zurk-800/80 border border-zurk-700/70 rounded-xl px-4 py-3">
      <p className="text-xs text-zurk-500 mb-1 uppercase tracking-[0.2em]">
        {label}
      </p>
      <p
        className={`text-2xl font-semibold tabular-nums ${accent ? 'text-accent-500' : 'text-zurk-100'}`}
      >
        {value}
      </p>
    </div>
  )
}
