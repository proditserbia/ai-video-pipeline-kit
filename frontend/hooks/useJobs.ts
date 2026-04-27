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
      const response = await api.get<PaginatedResponse<Job>>(`jobs?${params}`)
      return response.data
    },
  })
}

export function useJob(id: number | string) {
  return useQuery({
    queryKey: ['jobs', id],
    queryFn: async () => {
      const response = await api.get<Job>(`jobs/${id}`)
      return response.data
    },
    enabled: !!id,
  })
}

export function useJobStats() {
  return useQuery({
    queryKey: ['jobs', 'stats'],
    queryFn: async () => {
      const response = await api.get<JobStats>('jobs/stats')
      return response.data
    },
  })
}

export function useCreateJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (data: CreateJobRequest) => {
      const response = await api.post<Job>('jobs', data)
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
      const response = await api.post<Job>(`jobs/${id}/retry`)
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
      const response = await api.post<Job>(`jobs/${id}/cancel`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}

export function useDeleteJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`jobs/${id}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}

export function useDownloadJob() {
  return useMutation({
    mutationFn: async (job: Job) => {
      const response = await api.get(`jobs/${job.id}/download`, {
        responseType: 'blob',
      })
      const url = URL.createObjectURL(new Blob([response.data], { type: 'video/mp4' }))
      const link = document.createElement('a')
      link.href = url
      const disposition = response.headers['content-disposition'] as string | undefined
      const match = disposition?.match(/filename[^;=\n]*=(['"]?)([^'";\n]+)\1/)
      link.download = match ? match[2] : `${job.title}.mp4`
      link.click()
      URL.revokeObjectURL(url)
    },
  })
}
