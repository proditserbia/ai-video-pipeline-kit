export interface User {
  id: number
  email: string
  is_active: boolean
  is_admin: boolean
  created_at: string
}

export interface ProjectSettings {
  default_voice?: string
  default_caption_style?: string
  auto_publish?: boolean
  [key: string]: unknown
}

export interface Project {
  id: number
  user_id: number
  name: string
  description?: string | null
  brand_settings?: ProjectSettings | null
  default_voice?: string | null
  default_output_format: string
  job_count?: number
  created_at: string
  updated_at: string
}

export type JobStatus = 'pending' | 'processing' | 'rendering' | 'uploading' | 'completed' | 'failed' | 'cancelled'
export type CaptionStyle = 'none' | 'basic' | 'bold' | 'karaoke'
export type TopicStatus = 'pending' | 'approved' | 'rejected' | 'used'

export interface Job {
  id: string
  project_id: number | null
  user_id: number
  title: string
  status: JobStatus
  input_data?: Record<string, unknown> | null
  dry_run: boolean
  max_retries: number
  output_path?: string | null
  output_url?: string | null
  output_metadata?: Record<string, unknown> | null
  error_message?: string | null
  retry_count: number
  celery_task_id?: string | null
  validation_result?: Record<string, unknown> | null
  logs: string[]
  created_at: string
  updated_at: string
  started_at?: string | null
  completed_at?: string | null
  // Computed fields derived from input_data by the backend
  voice_name?: string | null
  caption_style?: string | null
  script?: string | null
  topic?: string | null
}

export interface Topic {
  id: number
  title: string
  description?: string | null
  source?: string | null
  score?: number | null
  keywords?: string[] | null
  status: TopicStatus
  created_at: string
}

export type AssetType = 'video' | 'audio' | 'image' | 'script' | 'other'

export interface Asset {
  id: number
  project_id?: number | null
  filename: string
  file_path: string
  file_type: string
  mime_type?: string | null
  source: string
  created_at: string
}

export interface LoginRequest {
  email: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: User
}

export interface CreateJobRequest {
  project_id: number
  title: string
  script?: string
  topic?: string
  voice_name: string
  caption_style: CaptionStyle
  dry_run: boolean
}

export interface CreateProjectRequest {
  name: string
  description?: string
  settings?: ProjectSettings
}

export interface UpdateProjectRequest {
  name?: string
  description?: string
  settings?: ProjectSettings
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  size: number
  pages: number
}

export interface JobStats {
  total: number
  completed: number
  failed: number
  processing: number
  pending: number
}

export type FeatureFlags = Record<string, boolean>

export interface CredentialStatus {
  openai: boolean
  edge_tts: boolean
  pexels: boolean
  pixabay: boolean
  youtube: boolean
}
