'use client'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { CheckCircle, XCircle, Info } from 'lucide-react'
import type { AppSettingsStatus } from '@/types'

function useSettingsStatus() {
  return useQuery({
    queryKey: ['settings', 'status'],
    queryFn: async () => (await api.get<AppSettingsStatus>('settings/status')).data,
  })
}

function StatusBadge({ ok, trueLabel = 'Enabled', falseLabel = 'Disabled' }: { ok: boolean; trueLabel?: string; falseLabel?: string }) {
  return ok
    ? <Badge className="bg-green-900 text-green-300 border-green-700">{trueLabel}</Badge>
    : <Badge className="bg-gray-800 text-gray-400 border-gray-600">{falseLabel}</Badge>
}

function KeyPresenceBadge({ present }: { present: boolean }) {
  return present
    ? <span className="flex items-center gap-1 text-xs text-green-400"><CheckCircle className="h-4 w-4" />Configured</span>
    : <span className="flex items-center gap-1 text-xs text-gray-500"><XCircle className="h-4 w-4" />Not configured</span>
}

function Row({ label, description, children }: { label: string; description?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between rounded-lg border border-gray-700 p-3 gap-4">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-200">{label}</p>
        {description && <p className="text-xs text-gray-500 mt-0.5">{description}</p>}
      </div>
      <div className="shrink-0 flex items-center">{children}</div>
    </div>
  )
}

function ValueCell({ value }: { value: string | number | null | undefined }) {
  return <span className="text-xs font-mono text-gray-300 bg-gray-800 px-2 py-0.5 rounded">{value ?? '—'}</span>
}

function EnvLabel() {
  return (
    <span className="flex items-center gap-1 text-xs text-gray-500 ml-2">
      <Info className="h-3 w-3" />Configured via .env
    </span>
  )
}

export default function SettingsPage() {
  const { data, isLoading, error } = useSettingsStatus()

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Settings</h1>
      <p className="text-sm text-gray-400">Read-only view of the current application configuration. All settings are configured via environment variables.</p>

      {isLoading && (
        <div className="flex justify-center py-12"><Spinner /></div>
      )}

      {error && (
        <Alert variant="destructive">
          <AlertDescription>Failed to load settings. Please try again later.</AlertDescription>
        </Alert>
      )}

      {data && (
        <div className="space-y-6">
          {/* General */}
          <Card>
            <CardHeader><CardTitle>General</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              <Row label="App Name"><ValueCell value={data.app_name} /></Row>
              <Row label="Environment">
                <ValueCell value={data.environment} />
              </Row>
              <Row label="Storage Path" description="Local filesystem path where videos and uploads are stored.">
                <ValueCell value={data.storage_path} /><EnvLabel />
              </Row>
            </CardContent>
          </Card>

          {/* Media Pipeline */}
          <Card>
            <CardHeader><CardTitle>Media Pipeline</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              <Row
                label="Media Mode"
                description="Controls whether the pipeline uses stock media or AI-generated images."
              >
                <ValueCell value={data.media.media_mode} /><EnvLabel />
              </Row>
              <Row
                label="AI Image Generation"
                description="Enables the script-scene-image-timeline pipeline with AI-generated visuals."
              >
                <StatusBadge ok={data.media.ai_image_enabled} /><EnvLabel />
              </Row>
              <Row label="AI Image Provider" description="Provider used to generate images (openai / stability / local_mock).">
                <ValueCell value={data.media.ai_image_provider} /><EnvLabel />
              </Row>
              <Row label="AI Image Aspect Ratio" description="Aspect ratio for generated images (9:16 for vertical video).">
                <ValueCell value={data.media.ai_image_aspect_ratio} /><EnvLabel />
              </Row>
              <Row
                label="Paragraph TTS Sync"
                description="Generates one audio file per narration block and syncs image durations to exact audio length."
              >
                <StatusBadge ok={data.media.paragraph_tts_sync_enabled} /><EnvLabel />
              </Row>
              <Row
                label="Visual Shot Plan"
                description="Varies image compositions by topic/category to avoid repetitive visuals."
              >
                <StatusBadge ok={data.media.visual_shot_plan_enabled} /><EnvLabel />
              </Row>
            </CardContent>
          </Card>

          {/* Script Generation */}
          <Card>
            <CardHeader><CardTitle>Script Generation</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              <Row label="AI Script Generation" description="Uses OpenAI to generate narration scripts from a topic or prompt.">
                <StatusBadge ok={data.script.ai_script_enabled} trueLabel="Active" falseLabel="Placeholder mode" /><EnvLabel />
              </Row>
              <Row label="Script Provider" description="Active script generation backend.">
                <ValueCell value={data.script.provider} /><EnvLabel />
              </Row>
            </CardContent>
          </Card>

          {/* TTS / Voice */}
          <Card>
            <CardHeader><CardTitle>TTS / Voice</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              <Row label="Active TTS Provider" description="Highest-priority text-to-speech provider based on current config.">
                <ValueCell value={data.tts.active_provider === 'none' ? 'None configured' : data.tts.active_provider} />
              </Row>
              <Row label="Default Voice" description="Default voice used when no explicit voice is specified.">
                <ValueCell value={data.tts.default_voice} />
              </Row>
              <Row label="OpenAI TTS"><StatusBadge ok={data.tts.openai_tts_available} trueLabel="Available" falseLabel="Not available" /><EnvLabel /></Row>
              <Row label="ElevenLabs TTS"><StatusBadge ok={data.tts.elevenlabs_available} trueLabel="Available" falseLabel="Not available" /><EnvLabel /></Row>
              <Row label="Coqui TTS (local)"><StatusBadge ok={data.tts.coqui_available} trueLabel="Enabled" falseLabel="Disabled" /><EnvLabel /></Row>
              <Row label="Edge TTS"><StatusBadge ok={data.tts.edge_tts_available} trueLabel="Enabled" falseLabel="Disabled" /><EnvLabel /></Row>
            </CardContent>
          </Card>

          {/* Captions */}
          <Card>
            <CardHeader><CardTitle>Captions</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              <Row label="Whisper Caption Engine" description="Uses faster-whisper to auto-generate synced captions from audio.">
                <StatusBadge ok={data.captions.whisper_enabled} /><EnvLabel />
              </Row>
              <Row label="Whisper Model Size" description="Larger models are more accurate but slower.">
                <ValueCell value={data.captions.model_size} /><EnvLabel />
              </Row>
              <Row label="Available Caption Styles" description="Styles that can be selected when creating a job.">
                <span className="text-xs text-gray-300">{data.captions.available_styles.join(', ')}</span>
              </Row>
            </CardContent>
          </Card>

          {/* API Keys / Providers */}
          <Card>
            <CardHeader>
              <CardTitle>API Keys / Providers</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <p className="text-xs text-gray-500 mb-3">Only shows whether each key is present — actual values are never exposed.</p>
              <Row label="OpenAI API Key"><KeyPresenceBadge present={data.providers.openai_api_key_present} /></Row>
              <Row label="Pexels API Key"><KeyPresenceBadge present={data.providers.pexels_api_key_present} /></Row>
              <Row label="Pixabay API Key"><KeyPresenceBadge present={data.providers.pixabay_api_key_present} /></Row>
              <Row label="Stability AI API Key"><KeyPresenceBadge present={data.providers.stability_api_key_present} /></Row>
              <Row label="ElevenLabs API Key"><KeyPresenceBadge present={data.providers.elevenlabs_api_key_present} /></Row>
            </CardContent>
          </Card>

          {/* Jobs / Automation */}
          <Card>
            <CardHeader><CardTitle>Jobs / Automation</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              <Row label="Max Job Retries" description="Number of times a failed job will be automatically retried.">
                <ValueCell value={data.jobs.max_retries} /><EnvLabel />
              </Row>
              <Row label="Dry Run Mode" description="When enabled, jobs run without producing real output (for testing).">
                <StatusBadge ok={data.jobs.dry_run} trueLabel="On" falseLabel="Off" /><EnvLabel />
              </Row>
              <Row label="Default Job Ordering"><ValueCell value={data.jobs.default_ordering.replace(/_/g, ' ')} /></Row>
            </CardContent>
          </Card>

          {/* Feature Flags */}
          <Card>
            <CardHeader><CardTitle>Feature Flags</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {Object.entries(data.feature_flags).map(([key, enabled]) => (
                <Row key={key} label={key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}>
                  <StatusBadge ok={enabled} />
                </Row>
              ))}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}

