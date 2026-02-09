import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { sessions } from '../api/client'
import type { SessionCreate, SessionPrompt, SessionWithMessages } from '../api/types'

const SESSIONS_KEY = ['sessions'] as const

export function useSessions(projectId?: string) {
  return useQuery({
    queryKey: [...SESSIONS_KEY, { projectId }],
    queryFn: () => sessions.list(projectId ? { project_id: projectId } : undefined),
    staleTime: 10_000,
  })
}

export function useSession(id: string) {
  return useQuery({
    queryKey: ['session', id],
    queryFn: () => sessions.get(id),
    enabled: !!id,
    refetchInterval: (query) => {
      // Poll more frequently when session is running or waiting approval
      const status = query.state.data?.status
      if (status === 'running' || status === 'waiting_approval') return 3_000
      return false
    },
  })
}

export function useSessionMessages(id: string) {
  return useQuery({
    queryKey: ['session', id, 'messages'],
    queryFn: () => sessions.messages(id),
    enabled: !!id,
    refetchInterval: 5_000,
  })
}

export function useCreateSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: SessionCreate) => sessions.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: SESSIONS_KEY }),
  })
}

export function useSendPrompt() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, prompt }: { id: string; prompt: string }) =>
      sessions.sendPrompt(id, { prompt } satisfies SessionPrompt),
    onSuccess: (_data, { id }) => {
      // Optimistically set status to 'running' so the UI immediately:
      // - hides the error banner (if retrying from error state)
      // - connects WebSocket (isActive becomes true)
      // - starts polling (refetchInterval returns 3000 for 'running')
      // Without this, there's a race: the refetch can return before the
      // background task transitions the status, leaving the UI stuck.
      qc.setQueryData<SessionWithMessages>(['session', id], (old) =>
        old ? { ...old, status: 'running', error_message: null } : old,
      )
      qc.invalidateQueries({ queryKey: ['session', id] })
      qc.invalidateQueries({ queryKey: SESSIONS_KEY })
    },
  })
}

export function useApproveSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, feedback }: { id: string; feedback?: string }) =>
      sessions.approve(id, feedback),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: ['session', id] })
    },
  })
}

export function useDenySession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, feedback }: { id: string; feedback?: string }) =>
      sessions.deny(id, feedback),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: ['session', id] })
    },
  })
}

export function useCancelSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => sessions.cancel(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ['session', id] })
      qc.invalidateQueries({ queryKey: SESSIONS_KEY })
    },
  })
}

export function useDeleteSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => sessions.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: SESSIONS_KEY }),
  })
}

export function useAllExternalSessions(limit = 50) {
  return useQuery({
    queryKey: ['external-sessions', 'all', limit],
    queryFn: () => sessions.allExternal(limit),
    staleTime: 60_000,
  })
}
