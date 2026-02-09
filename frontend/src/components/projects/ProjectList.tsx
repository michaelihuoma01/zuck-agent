import { Link } from 'react-router-dom'
import type { Project } from '../../api/types'
import EmptyState, { FolderIcon } from '../common/EmptyState'

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  })
}

export default function ProjectList({
  projects,
  onAddFirst,
}: {
  projects: Project[]
  onAddFirst?: () => void
}) {
  if (projects.length === 0) {
    return (
      <EmptyState
        icon={<FolderIcon />}
        title="No projects registered"
        description="Register a project directory to start managing Claude Code sessions for it."
        action={onAddFirst ? { label: 'Add First Project', onClick: onAddFirst } : undefined}
      />
    )
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {projects.map((project) => (
        <Link
          key={project.id}
          to={`/projects/${project.id}`}
          className="block p-4 rounded-xl bg-zurk-800 border border-zurk-700 hover:border-zurk-600 transition-colors group"
        >
          <h3 className="text-sm font-semibold text-zurk-100 group-hover:text-accent-400 transition-colors">
            {project.name}
          </h3>
          {project.description && (
            <p className="text-xs text-zurk-400 mt-1 line-clamp-2">
              {project.description}
            </p>
          )}
          <div className="flex items-center gap-3 mt-3 text-[11px] text-zurk-500">
            <span className="font-mono truncate max-w-[180px]" title={project.path}>
              {project.path}
            </span>
            <span className="ml-auto shrink-0">{formatDate(project.created_at)}</span>
          </div>
        </Link>
      ))}
    </div>
  )
}
