'use client'
import Link from 'next/link'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import JobStatusBadge from './JobStatusBadge'
import { formatRelativeDate } from '@/lib/utils'
import { useRetryJob, useCancelJob } from '@/hooks/useJobs'
import type { Job } from '@/types'
import { RefreshCw, XCircle, Eye } from 'lucide-react'

interface JobCardProps {
  job: Job
}

export default function JobCard({ job }: JobCardProps) {
  const retryJob = useRetryJob()
  const cancelJob = useCancelJob()

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <h3 className="truncate font-medium text-white">{job.title}</h3>
            <p className="mt-1 text-xs text-gray-400">
              Project #{job.project_id} · {formatRelativeDate(job.created_at)}
            </p>
          </div>
          <JobStatusBadge status={job.status} />
        </div>

        <div className="mt-4 flex items-center gap-2">
          <Button asChild size="sm" variant="outline">
            <Link href={`/jobs/${job.id}`}>
              <Eye className="mr-1 h-3 w-3" />
              View
            </Link>
          </Button>
          {job.status === 'failed' && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => retryJob.mutate(job.id)}
              isLoading={retryJob.isPending}
            >
              <RefreshCw className="mr-1 h-3 w-3" />
              Retry
            </Button>
          )}
          {(job.status === 'pending' || job.status === 'processing') && (
            <Button
              size="sm"
              variant="destructive"
              onClick={() => cancelJob.mutate(job.id)}
              isLoading={cancelJob.isPending}
            >
              <XCircle className="mr-1 h-3 w-3" />
              Cancel
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
