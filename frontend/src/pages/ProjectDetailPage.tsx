import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useProject, useDeleteProject, useExternalSessions } from '../hooks/useProjects'
import { useSessions, useCreateSession } from '../hooks/useSessions'
import SessionList from '../components/sessions/SessionList'
import ExternalSessionList from '../components/sessions/ExternalSessionList'
import { SessionListSkeleton } from '../components/common/Skeleton'
import Button from '../components/common/Button'
import PreviewButton, { usePreviewPort } from '../components/common/PreviewButton'
import { useToast } from '../components/common/Toast'
import EmptyState, { FolderIcon } from '../components/common/EmptyState'

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: project, isLoading } = useProject(id!)
  const { data: sessionData, isLoading: sessionsLoading } = useSessions(id)
  const { data: externalData, isLoading: externalLoading } = useExternalSessions(id!)
  const createSession = useCreateSession()
  const deleteProject = useDeleteProject()
  const { success, error: showError } = useToast()

  const [prompt, setPrompt] = useState('')
  const [showNewSession, setShowNewSession] = useState(false)
  const previewPort = usePreviewPort(project?.id ?? '')

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-48">
        <div className="flex flex-col items-center gap-3">
          <div className="w-6 h-6 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-zurk-400">Loading project...</p>
        </div>
      </div>
    )
  }

  if (!project) {
    return (
      <div className="flex items-center justify-center h-48">
        <EmptyState
          icon={<FolderIcon />}
          title="Project not found"
          description="This project may have been deleted or the URL is incorrect."
          action={{ label: 'View All Projects', onClick: () => navigate('/projects') }}
        />
      </div>
    )
  }

  const handleNewSession = async () => {
    if (!prompt.trim()) return
    try {
      const session = await createSession.mutateAsync({
        project_id: project.id,
        prompt: prompt.trim(),
      })
      setPrompt('')
      setShowNewSession(false)
      success('Session started')
      navigate(`/sessions/${session.id}`)
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to create session')
    }
  }

  const handleDelete = async () => {
    if (!window.confirm(`Delete project "${project.name}"? This will also delete all sessions.`)) return
    try {
      await deleteProject.mutateAsync(project.id)
      success(`Project "${project.name}" deleted`)
      navigate('/projects')
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to delete project')
    }
  }

  const sessions = sessionData?.sessions ?? []
  const toolsLabel = project.default_allowed_tools?.length
    ? `${project.default_allowed_tools.length} tools`
    : 'All tools'

  return (
    <div className="space-y-6 max-w-4xl">
      {/* ── Header ────────────────────────────────────────────────── */}
      <div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate('/projects')}
            className="shrink-0 p-1.5 -ml-1.5 rounded-md text-zurk-400 hover:text-white hover:bg-zurk-700/50 transition-colors"
            aria-label="Back to projects"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
            </svg>
          </button>
          <h1 className="text-2xl font-bold text-zurk-50 truncate">{project.name}</h1>
        </div>
        {project.description && (
          <p className="text-sm text-zurk-400 mt-1">{project.description}</p>
        )}
        <p className="text-xs text-zurk-500 font-mono mt-2 truncate">{project.path}</p>
        <div className="flex items-center gap-3 mt-2 text-[11px] text-zurk-500">
          <span>{project.permission_mode}</span>
          <span className="text-zurk-700">&middot;</span>
          <span>Created {new Date(project.created_at).toLocaleDateString()}</span>
        </div>
      </div>

      {/* ── Tools + Preview grid ──────────────────────────────────── */}
      <div className={`grid gap-3 ${project.dev_command ? 'grid-cols-2' : 'grid-cols-1'}`}>
        <div className="bg-zurk-800/80 border border-zurk-700/70 rounded-lg px-3 py-2.5">
          <p className="text-[10px] text-zurk-500 uppercase tracking-[0.2em]">Allowed Tools</p>
          <p className="text-sm text-zurk-200 font-medium mt-0.5">{toolsLabel}</p>
        </div>
        {project.dev_command && (
          <div className="bg-zurk-800/80 border border-zurk-700/70 rounded-lg px-3 py-2.5">
            <p className="text-[10px] text-zurk-500 uppercase tracking-[0.2em] mb-1">
              Live Preview{previewPort ? ` (:${previewPort})` : ''}
            </p>
            <PreviewButton projectId={project.id} devCommand={project.dev_command} size="sm" />
          </div>
        )}
      </div>

      {/* ── New session form ──────────────────────────────────────── */}
      {showNewSession && (
        <div className="bg-zurk-800/80 border border-zurk-700/70 rounded-xl p-4 space-y-3">
          <label className="block text-sm font-medium text-zurk-200">
            Initial Prompt
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="What should Claude work on?"
            rows={3}
            className="w-full bg-zurk-800/80 border border-zurk-600/70 rounded-lg px-3 py-2 text-sm
              text-zurk-100 placeholder:text-zurk-500 resize-none
              focus:outline-none focus:ring-2 focus:ring-accent-500/20 focus:border-accent-400"
          />
          <div className="flex gap-2">
            <Button
              onClick={handleNewSession}
              loading={createSession.isPending}
              disabled={!prompt.trim()}
            >
              Start Session
            </Button>
            <Button variant="ghost" onClick={() => setShowNewSession(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* ── Sessions ──────────────────────────────────────────────── */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold text-zurk-100">Sessions ({sessions.length})</h2>
          </div>
          <Button
            variant="primary"
            size="sm"
            onClick={() => setShowNewSession(true)}
          >
            New Session
          </Button>
        </div>
        <div className="bg-zurk-800/80 border border-zurk-700/70 rounded-xl">
          {sessionsLoading ? (
            <SessionListSkeleton count={3} />
          ) : (
            <SessionList sessions={sessions} projects={[project]} />
          )}
        </div>
      </section>

      {/* ── External Claude Code sessions ─────────────────────────── */}
      <section>
        <h2 className="text-lg font-semibold text-zurk-100 mb-3">
          Claude Code Sessions{externalData ? ` (${externalData.total})` : ''}
        </h2>
        <div className="bg-zurk-800/80 border border-zurk-700/70 rounded-xl">
          {externalLoading ? (
            <div className="flex items-center justify-center py-10">
              <div className="w-5 h-5 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : externalData ? (
            <ExternalSessionList
              sessions={externalData.sessions}
              claudeDir={externalData.claude_dir}
              projectId={id!}
            />
          ) : (
            <div className="text-center py-10">
              <p className="text-zurk-500 text-xs">
                Could not scan for external sessions
              </p>
            </div>
          )}
        </div>
      </section>

      {/* ── Danger zone ───────────────────────────────────────────── */}
      <div className="pt-4 border-t border-zurk-700/70">
        <button
          onClick={handleDelete}
          className="text-xs text-status-error hover:text-status-error/80 transition-colors"
        >
          Delete project
        </button>
      </div>
    </div>
  )
}
