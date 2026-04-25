import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { JobStatus } from '@/types'

interface JobStatusBadgeProps {
  status: JobStatus
}

export default function JobStatusBadge({ status }: JobStatusBadgeProps) {
  const config: Record<JobStatus, { label: string; className: string }> = {
    pending: { label: 'Pending', className: 'bg-gray-700 text-gray-300' },
    processing: { label: 'Processing', className: 'bg-blue-700 text-blue-100 animate-pulse' },
    rendering: { label: 'Rendering', className: 'bg-indigo-700 text-indigo-100' },
    uploading: { label: 'Uploading', className: 'bg-purple-700 text-purple-100' },
    completed: { label: 'Completed', className: 'bg-green-700 text-green-100' },
    failed: { label: 'Failed', className: 'bg-red-700 text-red-100' },
    cancelled: { label: 'Cancelled', className: 'bg-yellow-700 text-yellow-100' },
  }

  const { label, className } = config[status] || config.pending

  return (
    <Badge className={cn('font-medium', className)}>
      {label}
    </Badge>
  )
}
