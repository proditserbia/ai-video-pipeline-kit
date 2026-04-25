export interface User {
  id: number
  email: string
  username: string
  is_active: boolean
  is_superuser: boolean
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
  name: string
  description?: string
  settings: ProjectSettings
  job_count: number
  created_at: string
  updated_at: string
}

export type JobStatus = 'pending' | 'processing' | 'rendering' | 'uploading' | 'completed' | 'failed' | 'cancelled'
export type CaptionStyle = 'none' | 'basic' | 'bold' | 'karaoke'
export type TopicStatus = 'pending' | 'approved' | 'rejected'

export interface Job {
  id: number
  project_id: number
  title: string
  status: JobStatus
  script?: string
  topic?: string
  voice_name: string
  caption_style: CaptionStyle
  use_background_music: boolean
  dry_run: boolean
  output_url?: string
  error_message?: string
  logs: string[]
  created_at: string
  updated_at: string
}

export interface Topic {
  id: number
  project_id: number
  title: string
  description?: string
  score: number
  status: TopicStatus
  created_at: string
}

export type AssetType = 'video' | 'audio' | 'image' | 'script' | 'other'

export interface Asset {
  id: number
  project_id: number
  name: string
  file_path: string
  asset_type: AssetType
  file_size: number
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
  use_background_music: boolean
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
