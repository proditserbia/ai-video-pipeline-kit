'use client'
import { useEffect } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { useJob, useRetryJob, useCancelJob, useDownloadJob } from '@/hooks/useJobs'
import { useQueryClient } from '@tanstack/react-query'
import JobStatusBadge from '@/components/jobs/JobStatusBadge'
import ResultQualityBadge from '@/components/jobs/ResultQualityBadge'
import JobLogViewer from '@/components/jobs/JobLogViewer'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { formatDate } from '@/lib/utils'
import { ArrowLeft, RefreshCw, XCircle, Download, CheckCircle, AlertTriangle } from 'lucide-react'

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
            {job.result_quality && (
              <ResultQualityBadge quality={job.result_quality} />
            )}
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

      {job.result_quality && (
        <Card>
          <CardHeader><CardTitle>Quality Summary</CardTitle></CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div>
                <p className="text-xs text-gray-400">Overall Quality</p>
                <div className="mt-1">
                  <ResultQualityBadge quality={job.result_quality} />
                </div>
              </div>
              <div>
                <p className="text-xs text-gray-400">TTS Audio</p>
                <p className={`mt-1 text-sm font-medium ${
                  job.tts_status === 'success' ? 'text-green-400'
                  : job.tts_status === 'failed' ? 'text-red-400'
                  : job.tts_status === 'skipped' ? 'text-yellow-400'
                  : 'text-gray-400'
                }`}>
                  {job.tts_status ?? '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-400">Captions</p>
                <p className={`mt-1 text-sm font-medium ${
                  job.caption_status === 'success' ? 'text-green-400'
                  : job.caption_status === 'failed' ? 'text-red-400'
                  : job.caption_status === 'skipped' ? 'text-yellow-400'
                  : 'text-gray-400'
                }`}>
                  {job.caption_status ?? '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-400">Stock Media</p>
                <p className={`mt-1 text-sm font-medium ${
                  (job.output_metadata?.stock_provider as string | undefined) === 'placeholder'
                    ? 'text-orange-400'
                    : 'text-white'
                }`}>
                  {(job.output_metadata?.stock_provider as string | undefined) ?? '—'}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {job.warnings && job.warnings.length > 0 && (
        <div className="space-y-2">
          {job.warnings.map((w, i) => (
            <Alert key={`warning-${i}`} variant="warning">
              <AlertDescription>{w}</AlertDescription>
            </Alert>
          ))}
        </div>
      )}

      {job.script && (
        <Card>
          <CardHeader><CardTitle>Script</CardTitle></CardHeader>
          <CardContent>
            <pre className="whitespace-pre-wrap text-sm text-gray-300">{job.script}</pre>
          </CardContent>
        </Card>
      )}

      {job.validation_result && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Output Validation
              {job.validation_result.passed ? (
                <span className="flex items-center gap-1 text-xs font-normal text-green-400">
                  <CheckCircle className="h-3.5 w-3.5" />Passed
                </span>
              ) : (
                <span className="flex items-center gap-1 text-xs font-normal text-red-400">
                  <AlertTriangle className="h-3.5 w-3.5" />Failed
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div>
                <p className="text-xs text-gray-400">Has Audio</p>
                <p className={`mt-1 text-sm font-medium ${job.validation_result.has_audio ? 'text-green-400' : 'text-red-400'}`}>
                  {job.validation_result.has_audio ? 'Yes' : 'No'}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-400">Resolution</p>
                <p className="mt-1 text-sm font-medium text-white">
                  {job.validation_result.width && job.validation_result.height
                    ? `${job.validation_result.width}×${job.validation_result.height}`
                    : '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-400">Duration</p>
                <p className="mt-1 text-sm font-medium text-white">
                  {job.validation_result.duration ? `${job.validation_result.duration.toFixed(1)}s` : '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-400">File Size</p>
                <p className="mt-1 text-sm font-medium text-white">
                  {job.validation_result.file_size_bytes
                    ? `${(job.validation_result.file_size_bytes / 1024 / 1024).toFixed(1)} MB`
                    : '—'}
                </p>
              </div>
            </div>

            {job.validation_result.warnings.length > 0 && (
              <div className="space-y-1">
                {job.validation_result.warnings.map((w, i) => (
                  <Alert key={`vwarn-${i}`} variant="warning">
                    <AlertDescription>{w}</AlertDescription>
                  </Alert>
                ))}
              </div>
            )}

            {job.validation_result.errors.length > 0 && (
              <div className="space-y-1">
                {job.validation_result.errors.map((e, i) => (
                  <Alert key={`verr-${i}`} variant="destructive">
                    <AlertDescription>{e}</AlertDescription>
                  </Alert>
                ))}
              </div>
            )}
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

