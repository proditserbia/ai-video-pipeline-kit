'use client'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select } from '@/components/ui/select'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { useCreateJob } from '@/hooks/useJobs'
import { useProjects } from '@/hooks/useProjects'

const VOICES = [
  'en-US-AriaNeural',
  'en-US-GuyNeural',
  'en-US-JennyNeural',
  'en-US-DavisNeural',
  'en-GB-SoniaNeural',
  'en-GB-RyanNeural',
  'en-AU-NatashaNeural',
  'en-AU-WilliamNeural',
]

const schema = z.object({
  project_id: z.string().min(1, 'Project is required'),
  title: z.string().min(1, 'Title is required').max(200),
  script: z.string().optional(),
  topic: z.string().optional(),
  voice_name: z.string().min(1, 'Voice is required'),
  caption_style: z.enum(['none', 'basic', 'bold', 'karaoke']),
  use_background_music: z.boolean(),
  dry_run: z.boolean(),
})

type FormData = z.infer<typeof schema>

export default function CreateJobForm() {
  const router = useRouter()
  const [scriptMode, setScriptMode] = useState<'manual' | 'ai'>('manual')
  const [error, setError] = useState<string | null>(null)
  const createJob = useCreateJob()
  const { data: projects } = useProjects()

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      voice_name: 'en-US-AriaNeural',
      caption_style: 'basic',
      use_background_music: false,
      dry_run: false,
    },
  })

  const onSubmit = async (data: FormData) => {
    try {
      setError(null)
      const job = await createJob.mutateAsync({
        project_id: Number(data.project_id),
        title: data.title,
        script: scriptMode === 'manual' ? data.script : undefined,
        topic: scriptMode === 'ai' ? data.topic : undefined,
        voice_name: data.voice_name,
        caption_style: data.caption_style,
        use_background_music: data.use_background_music,
        dry_run: data.dry_run,
      })
      router.push(`/jobs/${job.id}`)
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } }
      setError(axiosErr.response?.data?.detail || 'Failed to create job')
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="space-y-2">
        <Label htmlFor="project_id">Project</Label>
        <Select id="project_id" {...register('project_id')}>
          <option value="">Select a project...</option>
          {projects?.items?.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </Select>
        {errors.project_id && <p className="text-xs text-red-400">{errors.project_id.message}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="title">Job Title</Label>
        <Input id="title" placeholder="My awesome video" {...register('title')} />
        {errors.title && <p className="text-xs text-red-400">{errors.title.message}</p>}
      </div>

      <div className="space-y-2">
        <Label>Script Mode</Label>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setScriptMode('manual')}
            className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              scriptMode === 'manual'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            Manual Script
          </button>
          <button
            type="button"
            onClick={() => setScriptMode('ai')}
            className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              scriptMode === 'ai'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            AI Generate
          </button>
        </div>
      </div>

      {scriptMode === 'manual' ? (
        <div className="space-y-2">
          <Label htmlFor="script">Script</Label>
          <Textarea
            id="script"
            rows={8}
            placeholder="Enter your video script here..."
            {...register('script')}
          />
        </div>
      ) : (
        <div className="space-y-2">
          <Label htmlFor="topic">Topic / Prompt</Label>
          <Input
            id="topic"
            placeholder="e.g. Top 5 productivity tips for developers"
            {...register('topic')}
          />
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="voice_name">Voice</Label>
          <Select id="voice_name" {...register('voice_name')}>
            {VOICES.map((v) => (
              <option key={v} value={v}>{v}</option>
            ))}
          </Select>
          {errors.voice_name && <p className="text-xs text-red-400">{errors.voice_name.message}</p>}
        </div>

        <div className="space-y-2">
          <Label htmlFor="caption_style">Caption Style</Label>
          <Select id="caption_style" {...register('caption_style')}>
            <option value="none">None</option>
            <option value="basic">Basic</option>
            <option value="bold">Bold</option>
            <option value="karaoke">Karaoke</option>
          </Select>
        </div>
      </div>

      <div className="flex gap-6">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-500"
            {...register('use_background_music')}
          />
          <span className="text-sm text-gray-300">Background Music</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-500"
            {...register('dry_run')}
          />
          <span className="text-sm text-gray-300">Dry Run (no upload)</span>
        </label>
      </div>

      <Button type="submit" isLoading={isSubmitting} className="w-full">
        Create Job
      </Button>
    </form>
  )
}
