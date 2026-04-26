'use client'
import { useEffect } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { useJob, useRetryJob, useCancelJob, useDownloadJob } from '@/hooks/useJobs'
import { useQueryClient } from '@tanstack/react-query'
import JobStatusBadge from '@/components/jobs/JobStatusBadge'
import JobLogViewer from '@/components/jobs/JobLogViewer'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { formatDate } from '@/lib/utils'
import { ArrowLeft, RefreshCw, XCircle, Download } from 'lucide-react'

export default function JobDetailPage() {
  const params = useParams()
  const id = params.id as string
  const { data: job, isLoading, error } = useJob(id)
  const retryJob = useRetryJob()
  const cancelJob = useCancelJob()
  const downloadJob = useDownloadJob()
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!job) return
    const isActive = job.status === 'processing' || job.status === 'rendering' || job.status === 'uploading'
    if (!isActive) return
    const interval = setInterval(() => {
      queryClient.invalidateQueries({ queryKey: ['jobs', id] })
    }, 5000)
    return () => clearInterval(interval)
  }, [job, id, queryClient])

  if (isLoading) {
    return <div className="flex justify-center py-12"><Spinner /></div>
  }

  if (error || !job) {
    return <Alert variant="destructive"><AlertDescription>Job not found</AlertDescription></Alert>
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button asChild variant="ghost" size="sm">
          <Link href="/jobs"><ArrowLeft className="mr-2 h-4 w-4" />Back</Link>
        </Button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold text-white">{job.title}</h1>
            <JobStatusBadge status={job.status} />
          </div>
        </div>
        <div className="flex gap-2">
          {job.status === 'failed' && (
            <Button size="sm" variant="secondary" onClick={() => retryJob.mutate(job.id)} isLoading={retryJob.isPending}>
              <RefreshCw className="mr-2 h-4 w-4" />Retry
            </Button>
          )}
          {(job.status === 'pending' || job.status === 'processing') && (
            <Button size="sm" variant="destructive" onClick={() => cancelJob.mutate(job.id)} isLoading={cancelJob.isPending}>
              <XCircle className="mr-2 h-4 w-4" />Cancel
            </Button>
          )}
          {job.output_url && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => downloadJob.mutate(job)}
              isLoading={downloadJob.isPending}
            >
              <Download className="mr-2 h-4 w-4" />Download
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { label: 'Project', value: `#${job.project_id}` },
          { label: 'Voice', value: job.voice_name },
          { label: 'Captions', value: job.caption_style },
          { label: 'Created', value: formatDate(job.created_at) },
        ].map((item) => (
          <Card key={item.label}>
            <CardContent className="p-4">
              <p className="text-xs text-gray-400">{item.label}</p>
              <p className="mt-1 text-sm font-medium text-white">{item.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {job.error_message && (
        <Alert variant="destructive">
          <AlertDescription>{job.error_message}</AlertDescription>
        </Alert>
      )}

      {(job.tts_status === 'skipped' || job.tts_status === 'failed') && (
        <Alert variant="warning">
          <AlertDescription>
            {job.tts_warning || 'TTS was skipped. Video was rendered without voiceover.'}
          </AlertDescription>
        </Alert>
      )}

      {job.script && (
        <Card>
          <CardHeader><CardTitle>Script</CardTitle></CardHeader>
          <CardContent>
            <pre className="whitespace-pre-wrap text-sm text-gray-300">{job.script}</pre>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>
            Logs
            {(job.status === 'processing' || job.status === 'rendering') && (
              <span className="ml-2 text-xs font-normal text-blue-400">(auto-refreshing)</span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <JobLogViewer logs={job.logs || []} />
        </CardContent>
      </Card>
    </div>
  )
}
