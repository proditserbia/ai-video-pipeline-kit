'use client'
import Link from 'next/link'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { formatRelativeDate } from '@/lib/utils'
import { useDeleteProject } from '@/hooks/useProjects'
import type { Project } from '@/types'
import { Edit, Trash2, Film } from 'lucide-react'

interface ProjectCardProps {
  project: Project
}

export default function ProjectCard({ project }: ProjectCardProps) {
  const deleteProject = useDeleteProject()

  const handleDelete = () => {
    if (confirm('Delete this project?')) {
      deleteProject.mutate(project.id)
    }
  }

  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-white truncate">{project.name}</h3>
            <p className="mt-1 text-sm text-gray-400 line-clamp-2">
              {project.description || 'No description'}
            </p>
          </div>
        </div>

        <div className="mt-3 flex items-center gap-3 text-xs text-gray-500">
          <span className="flex items-center gap-1">
            <Film className="h-3 w-3" />
            {project.job_count ?? 0} jobs
          </span>
          <span>{formatRelativeDate(project.created_at)}</span>
        </div>

        <div className="mt-4 flex gap-2">
          <Button asChild size="sm" variant="outline" className="flex-1">
            <Link href={`/projects/${project.id}`}>
              <Edit className="mr-1 h-3 w-3" />
              Edit
            </Link>
          </Button>
          <Button
            size="sm"
            variant="destructive"
            onClick={handleDelete}
            isLoading={deleteProject.isPending}
          >
            <Trash2 className="h-3 w-3" />
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
