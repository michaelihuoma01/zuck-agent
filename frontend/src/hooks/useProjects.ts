import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projects, filesystem } from '../api/client'
import type { ProjectCreate, ProjectUpdate, ContinueExternalSessionRequest } from '../api/types'

const PROJECTS_KEY = ['projects'] as const
const EXTERNAL_SESSIONS_KEY = 'external-sessions' as const

export function useProjects() {
  return useQuery({
    queryKey: PROJECTS_KEY,
    queryFn: () => projects.list(),
    staleTime: 30_000,
  })
}

export function useProject(id: string) {
  return useQuery({
    queryKey: ['project', id],
    queryFn: () => projects.get(id),
    enabled: !!id,
  })
}

export function useCreateProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ProjectCreate) => projects.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: PROJECTS_KEY }),
  })
}

export function useUpdateProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ProjectUpdate }) =>
      projects.update(id, data),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: PROJECTS_KEY })
      qc.invalidateQueries({ queryKey: ['project', id] })
    },
  })
}

export function useDeleteProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => projects.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: PROJECTS_KEY }),
  })
}

export function useExternalSessions(projectId: string) {
  return useQuery({
    queryKey: [EXTERNAL_SESSIONS_KEY, projectId],
    queryFn: () => projects.externalSessions(projectId),
    enabled: !!projectId,
    staleTime: 60_000, // External sessions change rarely
  })
}

export function useExternalSessionDetail(projectId: string, sessionId: string) {
  return useQuery({
    queryKey: [EXTERNAL_SESSIONS_KEY, projectId, sessionId],
    queryFn: () => projects.externalSessionDetail(projectId, sessionId),
    enabled: !!projectId && !!sessionId,
  })
}

export function useBrowseDirectory(path?: string) {
  return useQuery({
    queryKey: ['filesystem', 'browse', path ?? 'home'],
    queryFn: () => filesystem.browse(path),
    staleTime: 30_000,
  })
}

export function useContinueExternalSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      projectId,
      sessionId,
      data,
    }: {
      projectId: string
      sessionId: string
      data: ContinueExternalSessionRequest
    }) => projects.continueExternalSession(projectId, sessionId, data),
    onSuccess: () => {
      // Invalidate session lists since a new session was created
      qc.invalidateQueries({ queryKey: ['sessions'] })
    },
  })
}
