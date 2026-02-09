import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projects } from '../api/client'
import type { PreviewStatus } from '../api/types'

const PREVIEW_KEY = 'preview' as const

function usePreviewStatus(projectId: string) {
  return useQuery({
    queryKey: [PREVIEW_KEY, projectId],
    queryFn: () => projects.preview.status(projectId),
    enabled: !!projectId,
    refetchInterval: (query) => {
      const data = query.state.data as PreviewStatus | undefined
      if (data?.running) return 5_000
      return false
    },
  })
}

function useStartPreview(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => projects.preview.start(projectId),
    onSuccess: (data) => {
      // Put the start response directly into the status cache
      // so the UI immediately sees running=true with URL, or running=false with error
      qc.setQueryData([PREVIEW_KEY, projectId], data)
    },
  })
}

function useStopPreview(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => projects.preview.stop(projectId),
    onSuccess: (data) => {
      qc.setQueryData([PREVIEW_KEY, projectId], data)
    },
  })
}

export function usePreview(projectId: string) {
  const { data: status, isLoading } = usePreviewStatus(projectId)
  const start = useStartPreview(projectId)
  const stop = useStopPreview(projectId)

  return { status, isLoading, start, stop }
}
