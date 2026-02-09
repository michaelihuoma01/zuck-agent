import { NavLink } from 'react-router-dom'
import { useProjects } from '../../hooks/useProjects'
import { useSessions } from '../../hooks/useSessions'

function NavItem({
  to,
  children,
  count,
}: {
  to: string
  children: React.ReactNode
  count?: number
}) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${
          isActive
            ? 'bg-accent-500/15 text-accent-400'
            : 'text-zurk-300 hover:bg-zurk-700 hover:text-zurk-100'
        }`
      }
    >
      <span className="truncate">{children}</span>
      {count !== undefined && count > 0 && (
        <span className="ml-2 text-xs tabular-nums text-zurk-400 bg-zurk-700 px-1.5 py-0.5 rounded-full">
          {count}
        </span>
      )}
    </NavLink>
  )
}

export default function Sidebar() {
  const { data: projectData } = useProjects()
  const { data: sessionData } = useSessions()

  const projects = projectData?.projects ?? []
  const runningSessions =
    sessionData?.sessions.filter(
      (s) => s.status === 'running' || s.status === 'waiting_approval',
    ).length ?? 0

  return (
    <aside className="fixed inset-y-0 left-0 z-30 w-sidebar border-r border-zurk-700 bg-zurk-800/90 backdrop-blur hidden md:flex flex-col">
      {/* Logo */}
      <div className="flex items-center gap-2 px-4 h-14 border-b border-zurk-700/70">
        <div className="w-7 h-7 rounded-lg bg-zurk-700 border border-zurk-600 flex items-center justify-center">
          <span className="text-zurk-50 font-semibold text-xs">Z</span>
        </div>
        <span className="font-medium text-zurk-50 tracking-[0.08em] text-xs">ZURK</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
        {/* Main nav */}
        <div className="space-y-1">
          <p className="px-3 text-[11px] font-medium text-zurk-400 uppercase tracking-wider mb-2">
            General
          </p>
          <NavItem to="/" count={runningSessions}>
            Dashboard
          </NavItem>
          <NavItem to="/projects" count={projects.length}>
            Projects
          </NavItem>
          <NavItem to="/settings">Settings</NavItem>
        </div>

        {/* Projects list */}
        {projects.length > 0 && (
          <div className="space-y-1">
            <p className="px-3 text-[11px] font-medium text-zurk-400 uppercase tracking-wider mb-2">
              Projects
            </p>
            {projects.map((project) => (
              <NavItem key={project.id} to={`/projects/${project.id}`}>
                {project.name}
              </NavItem>
            ))}
          </div>
        )}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-zurk-700/70">
        <p className="text-[11px] text-zurk-500">Agent Command Center</p>
      </div>
    </aside>
  )
}
