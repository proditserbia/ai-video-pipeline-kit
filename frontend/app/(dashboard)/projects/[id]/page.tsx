'use client'
import { useState } from 'react'
import { useParams } from 'next/navigation'
import { useProject, useUpdateProject } from '@/hooks/useProjects'
import { useJobs } from '@/hooks/useJobs'
import ProjectForm from '@/components/projects/ProjectForm'
import JobStatusBadge from '@/components/jobs/JobStatusBadge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { formatRelativeDate } from '@/lib/utils'
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'

export default function ProjectDetailPage() {
  const params = useParams()
  const id = params.id as string
  const { data: project, isLoading } = useProject(id)
  const { data: jobs } = useJobs({ project_id: Number(id) })
  const updateProject = useUpdateProject()
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleUpdate = async (data: { name: string; description?: string }) => {
    try {
      setError(null)
      setSuccess(false)
      await updateProject.mutateAsync({ id: Number(id), data })
      setSuccess(true)
    } catch {
      setError('Failed to update project')
    }
  }

  if (isLoading) {
    return <div className="flex justify-center py-12"><Spinner /></div>
  }

  if (!project) {
    return <Alert variant="destructive"><AlertDescription>Project not found</AlertDescription></Alert>
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button asChild variant="ghost" size="sm">
          <Link href="/projects"><ArrowLeft className="mr-2 h-4 w-4" />Back</Link>
        </Button>
        <h1 className="text-2xl font-bold text-white">{project.name}</h1>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Edit Project</CardTitle></CardHeader>
          <CardContent>
            {success && (
              <Alert variant="success" className="mb-4">
                <AlertDescription>Project updated successfully</AlertDescription>
              </Alert>
            )}
            {error && (
              <Alert variant="destructive" className="mb-4">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <ProjectForm
              onSubmit={handleUpdate}
              defaultValues={project}
              isLoading={updateProject.isPending}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Jobs ({jobs?.total ?? 0})</CardTitle></CardHeader>
          <CardContent>
            {jobs?.items?.length === 0 ? (
              <p className="text-sm text-gray-400">No jobs for this project yet</p>
            ) : (
              <div className="space-y-2">
                {jobs?.items?.map((job) => (
                  <div key={job.id} className="flex items-center justify-between rounded-lg border border-gray-700 p-3">
                    <div>
                      <p className="text-sm font-medium text-white">{job.title}</p>
                      <p className="text-xs text-gray-400">{formatRelativeDate(job.created_at)}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <JobStatusBadge status={job.status} />
                      <Button asChild size="sm" variant="ghost">
                        <Link href={`/jobs/${job.id}`}>View</Link>
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
