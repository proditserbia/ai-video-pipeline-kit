'use client'
import { useState } from 'react'
import { useTopics, useDiscoverTopics } from '@/hooks/useTopics'
import { useProjects } from '@/hooks/useProjects'
import TopicCard from '@/components/topics/TopicCard'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Lightbulb } from 'lucide-react'

export default function TopicsPage() {
  const [projectFilter, setProjectFilter] = useState<string>('')
  const { data: topics, isLoading, error } = useTopics(projectFilter ? Number(projectFilter) : undefined)
  const { data: projects } = useProjects()
  const discoverTopics = useDiscoverTopics()
  const [discoverError, setDiscoverError] = useState<string | null>(null)

  const handleDiscover = async () => {
    if (!projectFilter) { setDiscoverError('Please select a project first'); return }
    try {
      setDiscoverError(null)
      await discoverTopics.mutateAsync(Number(projectFilter))
    } catch { setDiscoverError('Failed to discover topics') }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Topics</h1>
        <Button onClick={handleDiscover} isLoading={discoverTopics.isPending}>
          <Lightbulb className="mr-2 h-4 w-4" />Discover Topics
        </Button>
      </div>
      {discoverError && <Alert variant="destructive"><AlertDescription>{discoverError}</AlertDescription></Alert>}
      <Select value={projectFilter} onChange={(e) => setProjectFilter(e.target.value)} className="w-48">
        <option value="">All Projects</option>
        {projects?.items?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </Select>
      {isLoading ? <div className="flex justify-center py-12"><Spinner /></div>
       : error ? <Alert variant="destructive"><AlertDescription>Failed to load topics</AlertDescription></Alert>
       : topics?.items?.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-gray-400">
          <Lightbulb className="mb-3 h-12 w-12 opacity-30" /><p>No topics yet. Discover some!</p>
        </div>
       ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {topics?.items?.map((topic) => <TopicCard key={topic.id} topic={topic} />)}
        </div>
       )}
    </div>
  )
}
