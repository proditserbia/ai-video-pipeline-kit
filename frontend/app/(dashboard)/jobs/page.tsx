'use client'
import { useState } from 'react'
import Link from 'next/link'
import { useJobs, useRetryJob, useCancelJob } from '@/hooks/useJobs'
import { useProjects } from '@/hooks/useProjects'
import JobStatusBadge from '@/components/jobs/JobStatusBadge'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatRelativeDate } from '@/lib/utils'
import type { JobStatus } from '@/types'
import { Plus, RefreshCw, XCircle, Eye } from 'lucide-react'

export default function JobsPage() {
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [projectFilter, setProjectFilter] = useState<string>('')
  const [page, setPage] = useState(1)

  const { data: jobs, isLoading, error, refetch } = useJobs({
    status: statusFilter as JobStatus || undefined,
    project_id: projectFilter ? Number(projectFilter) : undefined,
    page,
    size: 20,
  })
  const { data: projects } = useProjects()
  const retryJob = useRetryJob()
  const cancelJob = useCancelJob()

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Jobs</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
          <Button asChild size="sm">
            <Link href="/jobs/new">
              <Plus className="mr-2 h-4 w-4" />
              New Job
            </Link>
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <Select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }}
          className="w-40"
        >
          <option value="">All Statuses</option>
          <option value="pending">Pending</option>
          <option value="processing">Processing</option>
          <option value="rendering">Rendering</option>
          <option value="uploading">Uploading</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
        </Select>

        <Select
          value={projectFilter}
          onChange={(e) => { setProjectFilter(e.target.value); setPage(1) }}
          className="w-48"
        >
          <option value="">All Projects</option>
          {projects?.items?.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </Select>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12"><Spinner /></div>
      ) : error ? (
        <Alert variant="destructive"><AlertDescription>Failed to load jobs</AlertDescription></Alert>
      ) : (
        <>
          <div className="rounded-lg border border-gray-700 bg-gray-800">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Title</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Project</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs?.items?.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="py-12 text-center text-gray-400">
                      No jobs found
                    </TableCell>
                  </TableRow>
                ) : (
                  jobs?.items?.map((job) => (
                    <TableRow key={job.id}>
                      <TableCell className="font-medium">{job.title}</TableCell>
                      <TableCell><JobStatusBadge status={job.status} /></TableCell>
                      <TableCell>#{job.project_id}</TableCell>
                      <TableCell>{formatRelativeDate(job.created_at)}</TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-2">
                          <Button asChild size="sm" variant="ghost">
                            <Link href={`/jobs/${job.id}`}><Eye className="h-4 w-4" /></Link>
                          </Button>
                          {job.status === 'failed' && (
                            <Button size="sm" variant="secondary" onClick={() => retryJob.mutate(job.id)}>
                              <RefreshCw className="h-4 w-4" />
                            </Button>
                          )}
                          {(job.status === 'pending' || job.status === 'processing') && (
                            <Button size="sm" variant="destructive" onClick={() => cancelJob.mutate(job.id)}>
                              <XCircle className="h-4 w-4" />
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          {jobs && jobs.pages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </Button>
              <span className="text-sm text-gray-400">
                Page {page} of {jobs.pages}
              </span>
              <Button
                size="sm"
                variant="outline"
                disabled={page === jobs.pages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
