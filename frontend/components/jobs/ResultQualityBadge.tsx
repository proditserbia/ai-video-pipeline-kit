import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type ResultQuality = 'complete' | 'partial' | 'fallback'

interface ResultQualityBadgeProps {
  quality: ResultQuality
}

const config: Record<ResultQuality, { label: string; className: string }> = {
  complete: { label: 'Complete', className: 'bg-green-800 text-green-100' },
  partial: { label: 'Partial', className: 'bg-yellow-700 text-yellow-100' },
  fallback: { label: 'Fallback', className: 'bg-orange-700 text-orange-100' },
}

export default function ResultQualityBadge({ quality }: ResultQualityBadgeProps) {
  const { label, className } = config[quality] ?? config.complete
  return (
    <Badge className={cn('font-medium', className)}>
      {label}
    </Badge>
  )
}
