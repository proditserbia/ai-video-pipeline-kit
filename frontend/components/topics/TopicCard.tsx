'use client'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useApproveTopicMutation, useRejectTopicMutation } from '@/hooks/useTopics'
import type { Topic } from '@/types'
import { Check, X } from 'lucide-react'

interface TopicCardProps {
  topic: Topic
}

export default function TopicCard({ topic }: TopicCardProps) {
  const approve = useApproveTopicMutation()
  const reject = useRejectTopicMutation()

  const statusVariant: Record<string, 'success' | 'destructive' | 'secondary'> = {
    approved: 'success',
    rejected: 'destructive',
    pending: 'secondary',
  }

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-medium text-white">{topic.title}</h3>
          <Badge variant={statusVariant[topic.status] || 'secondary'}>
            {topic.status}
          </Badge>
        </div>

        {topic.description && (
          <p className="mt-2 text-sm text-gray-400">{topic.description}</p>
        )}

        <div className="mt-2 text-xs text-gray-500">Score: {topic.score != null ? topic.score.toFixed(2) : '—'}</div>

        {topic.status === 'pending' && (
          <div className="mt-3 flex gap-2">
            <Button
              size="sm"
              variant="default"
              onClick={() => approve.mutate(topic.id)}
              isLoading={approve.isPending}
              className="flex-1 bg-green-700 hover:bg-green-600"
            >
              <Check className="mr-1 h-3 w-3" />
              Approve
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => reject.mutate(topic.id)}
              isLoading={reject.isPending}
              className="flex-1"
            >
              <X className="mr-1 h-3 w-3" />
              Reject
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
