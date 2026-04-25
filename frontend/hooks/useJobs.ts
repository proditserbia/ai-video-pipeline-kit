import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import type { Job, CreateJobRequest, PaginatedResponse, JobStats, JobStatus } from '@/types'

interface JobFilters {
  project_id?: number
  status?: JobStatus
  page?: number
  size?: number
}

export function useJobs(filters: JobFilters = {}) {
  return useQuery({
    queryKey: ['jobs', filters],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (filters.project_id) params.set('project_id', String(filters.project_id))
      if (filters.status) params.set('status', filters.status)
      if (filters.page) params.set('page', String(filters.page))
      if (filters.size) params.set('size', String(filters.size))
      const response = await api.get<PaginatedResponse<Job>>(`/api/v1/jobs?${params}`)
      return response.data
    },
  })
}

export function useJob(id: number | string) {
  return useQuery({
    queryKey: ['jobs', id],
    queryFn: async () => {
      const response = await api.get<Job>(`/api/v1/jobs/${id}`)
      return response.data
    },
    enabled: !!id,
  })
}

export function useJobStats() {
  return useQuery({
    queryKey: ['jobs', 'stats'],
    queryFn: async () => {
      const response = await api.get<JobStats>('/api/v1/jobs/stats')
      return response.data
    },
  })
}

export function useCreateJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (data: CreateJobRequest) => {
      const response = await api.post<Job>('/api/v1/jobs', data)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}

export function useRetryJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const response = await api.post<Job>(`/api/v1/jobs/${id}/retry`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}

export function useCancelJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const response = await api.post<Job>(`/api/v1/jobs/${id}/cancel`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}
