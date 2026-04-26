import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import type { Topic, PaginatedResponse } from '@/types'

export function useTopics(projectId?: number) {
  return useQuery({
    queryKey: ['topics', projectId],
    queryFn: async () => {
      const params = projectId ? `?project_id=${projectId}` : ''
      const response = await api.get<PaginatedResponse<Topic>>(`topics${params}`)
      return response.data
    },
  })
}

export function useDiscoverTopics() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (projectId: number) => {
      const response = await api.post<Topic[]>('topics/discover', { project_id: projectId })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['topics'] })
    },
  })
}

export function useApproveTopicMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      const response = await api.post<Topic>(`topics/${id}/approve`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['topics'] })
    },
  })
}

export function useRejectTopicMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      const response = await api.post<Topic>(`topics/${id}/reject`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['topics'] })
    },
  })
}
