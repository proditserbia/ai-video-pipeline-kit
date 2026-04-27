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
export type CaptionStyle = 'none' | 'basic' | 'bold_center' | 'boxed' | 'large_bottom' | 'karaoke_placeholder'
export type TopicStatus = 'pending' | 'approved' | 'rejected' | 'used'

export interface ValidationResult {
  passed: boolean
  width: number
  height: number
  duration: number
  has_audio: boolean
  video_codec: string
  audio_codec: string
  file_size_bytes: number
  errors: string[]
  warnings: string[]
}

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
  thumbnail_url?: string | null
  output_metadata?: Record<string, unknown> | null
  error_message?: string | null
  retry_count: number
  celery_task_id?: string | null
  validation_result?: ValidationResult | null
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
  /** Script generation instructions (separate from topic). */
  prompt?: string | null
  /** Visual planning tags resolved from input_data. */
  visual_tags?: string[] | null
  // TTS outcome fields derived from output_metadata by the backend
  tts_status?: 'success' | 'skipped' | 'failed' | null
  tts_warning?: string | null
  // Caption outcome fields derived from output_metadata by the backend
  caption_status?: 'success' | 'skipped' | 'failed' | null
  caption_warning?: string | null
  // Result quality and warnings derived from output_metadata by the backend
  result_quality?: 'complete' | 'partial' | 'fallback' | null
  warnings?: string[] | null
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
  name?: string | null
  filename: string
  file_path: string
  file_type: string
  asset_type: AssetType
  file_size?: number | null
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
  /** Script generation guidance: tone, audience, angle, etc. Separate from topic. */
  prompt?: string
  /** Comma-separated visual tags or array (e.g. "architecture, soldiers"). */
  visual_tags?: string | string[]
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

export interface AppSettingsMedia {
  media_mode: string
  ai_image_enabled: boolean
  ai_image_provider: string
  ai_image_aspect_ratio: string
  paragraph_tts_sync_enabled: boolean
  visual_shot_plan_enabled: boolean
}

export interface AppSettingsScript {
  ai_script_enabled: boolean
  provider: string
}

export interface AppSettingsTTS {
  active_provider: string
  openai_tts_available: boolean
  edge_tts_available: boolean
  coqui_available: boolean
  elevenlabs_available: boolean
  default_voice: string | null
}

export interface AppSettingsCaptions {
  whisper_enabled: boolean
  model_size: string
  available_styles: string[]
}

export interface AppSettingsProviders {
  openai_api_key_present: boolean
  pexels_api_key_present: boolean
  pixabay_api_key_present: boolean
  stability_api_key_present: boolean
  elevenlabs_api_key_present: boolean
}

export interface AppSettingsJobs {
  max_retries: number
  dry_run: boolean
  default_ordering: string
}

export interface AppSettingsStatus {
  app_name: string
  environment: string
  storage_path: string
  media: AppSettingsMedia
  script: AppSettingsScript
  tts: AppSettingsTTS
  captions: AppSettingsCaptions
  providers: AppSettingsProviders
  jobs: AppSettingsJobs
  feature_flags: Record<string, boolean>
}
