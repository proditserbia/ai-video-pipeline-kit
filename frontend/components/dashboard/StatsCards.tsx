'use client'
import { Card, CardContent } from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
import { useJobStats } from '@/hooks/useJobs'
import { Film, CheckCircle, XCircle, Clock } from 'lucide-react'

export default function StatsCards() {
  const { data: stats, isLoading } = useJobStats()

  const cards = [
    { label: 'Total Jobs', value: stats?.total ?? 0, icon: Film, color: 'text-blue-400', bg: 'bg-blue-900/30' },
    { label: 'Completed', value: stats?.completed ?? 0, icon: CheckCircle, color: 'text-green-400', bg: 'bg-green-900/30' },
    { label: 'Failed', value: stats?.failed ?? 0, icon: XCircle, color: 'text-red-400', bg: 'bg-red-900/30' },
    { label: 'Processing', value: stats?.processing ?? 0, icon: Clock, color: 'text-yellow-400', bg: 'bg-yellow-900/30' },
  ]

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => {
        const Icon = card.icon
        return (
          <Card key={card.label}>
            <CardContent className="flex items-center gap-4 p-6">
              <div className={`flex h-12 w-12 items-center justify-center rounded-xl ${card.bg}`}>
                <Icon className={`h-6 w-6 ${card.color}`} />
              </div>
              <div>
                <p className="text-sm text-gray-400">{card.label}</p>
                {isLoading ? (
                  <Spinner size="sm" />
                ) : (
                  <p className="text-2xl font-bold text-white">{card.value}</p>
                )}
              </div>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
