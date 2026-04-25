'use client'
import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import type { Project } from '@/types'

const schema = z.object({
  name: z.string().min(1, 'Name is required').max(100),
  description: z.string().optional(),
})

type FormData = z.infer<typeof schema>

interface ProjectFormProps {
  onSubmit: (data: FormData) => Promise<void>
  defaultValues?: Partial<Project>
  isLoading?: boolean
}

export default function ProjectForm({ onSubmit, defaultValues, isLoading }: ProjectFormProps) {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: defaultValues?.name || '',
      description: defaultValues?.description || '',
    },
  })

  useEffect(() => {
    if (defaultValues) {
      reset({ name: defaultValues.name, description: defaultValues.description })
    }
  }, [defaultValues, reset])

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="name">Project Name</Label>
        <Input id="name" placeholder="My Video Project" {...register('name')} />
        {errors.name && <p className="text-xs text-red-400">{errors.name.message}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="description">Description</Label>
        <Textarea
          id="description"
          placeholder="Optional description..."
          {...register('description')}
        />
      </div>

      <Button type="submit" isLoading={isLoading} className="w-full">
        {defaultValues ? 'Update Project' : 'Create Project'}
      </Button>
    </form>
  )
}
