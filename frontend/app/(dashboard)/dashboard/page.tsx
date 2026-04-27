'use client'
import Link from 'next/link'
import StatsCards from '@/components/dashboard/StatsCards'
import { useJobs } from '@/hooks/useJobs'
import JobStatusBadge from '@/components/jobs/JobStatusBadge'
import JobThumbnail from '@/components/jobs/JobThumbnail'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { formatRelativeDate } from '@/lib/utils'
import { Plus, RefreshCw } from 'lucide-react'

export default function DashboardPage() {
  const { data: jobs, isLoading, refetch } = useJobs({ size: 10 })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
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

      <StatsCards />

      <div>
        <h2 className="mb-4 text-lg font-semibold text-white">Recent Jobs</h2>
        {isLoading ? (
          <div className="flex justify-center py-8">
            <Spinner />
          </div>
        ) : (
          <div className="rounded-lg border border-gray-700 bg-gray-800 overflow-hidden">
            {jobs?.items?.length === 0 ? (
              <div className="py-12 text-center text-gray-400">
                No jobs yet.{' '}
                <Link href="/jobs/new" className="text-blue-400 hover:underline">
                  Create your first job
                </Link>
              </div>
            ) : (
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-700">
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 w-14">Preview</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Title</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Status</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-400">Created</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-400">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs?.items?.map((job) => (
                    <tr key={job.id} className="border-b border-gray-700 last:border-0 hover:bg-gray-700/50">
                      <td className="px-4 py-3 w-14">
                        {job.thumbnail_url ? (
                          <JobThumbnail
                            jobId={job.id}
                            className="h-14 w-8 rounded object-cover"
                            alt={job.title}
                          />
                        ) : (
                          <div className="h-14 w-8 rounded bg-gray-700" />
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-white">{job.title}</td>
                      <td className="px-4 py-3">
                        <JobStatusBadge status={job.status} />
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-400">
                        {formatRelativeDate(job.created_at)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Button asChild size="sm" variant="ghost">
                          <Link href={`/jobs/${job.id}`}>View</Link>
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
