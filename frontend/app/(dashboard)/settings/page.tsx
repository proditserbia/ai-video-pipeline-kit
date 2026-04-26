'use client'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { CheckCircle, XCircle } from 'lucide-react'
import type { FeatureFlags, CredentialStatus } from '@/types'

function useFeatureFlags() {
  return useQuery({ queryKey: ['settings', 'features'], queryFn: async () => (await api.get<FeatureFlags>('settings/features')).data })
}
function useCredentialStatus() {
  return useQuery({ queryKey: ['settings', 'credentials'], queryFn: async () => (await api.get<CredentialStatus>('settings/credentials')).data })
}
function StatusIcon({ ok }: { ok: boolean }) {
  return ok ? <CheckCircle className="h-5 w-5 text-green-400" /> : <XCircle className="h-5 w-5 text-red-400" />
}

export default function SettingsPage() {
  const { data: features, isLoading: fl, error: fe } = useFeatureFlags()
  const { data: credentials, isLoading: cl, error: ce } = useCredentialStatus()
  const credentialLabels: Record<keyof CredentialStatus, string> = { openai: 'OpenAI API', edge_tts: 'Edge TTS', pexels: 'Pexels API', pixabay: 'Pixabay API', youtube: 'YouTube API' }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Settings</h1>
      <Card>
        <CardHeader><CardTitle>Credential Status</CardTitle></CardHeader>
        <CardContent>
          {cl ? <div className="flex justify-center py-6"><Spinner /></div>
           : ce ? <Alert variant="destructive"><AlertDescription>Failed to load credentials</AlertDescription></Alert>
           : <div className="space-y-3">{credentials && Object.entries(credentialLabels).map(([key, label]) => (
            <div key={key} className="flex items-center justify-between rounded-lg border border-gray-700 p-3">
              <span className="text-sm font-medium text-gray-200">{label}</span>
              <div className="flex items-center gap-2">
                <StatusIcon ok={credentials[key as keyof CredentialStatus]} />
                <span className={`text-xs ${credentials[key as keyof CredentialStatus] ? 'text-green-400' : 'text-red-400'}`}>
                  {credentials[key as keyof CredentialStatus] ? 'Configured' : 'Not configured'}
                </span>
              </div>
            </div>
          ))}</div>}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Feature Flags</CardTitle></CardHeader>
        <CardContent>
          {fl ? <div className="flex justify-center py-6"><Spinner /></div>
           : fe ? <Alert variant="destructive"><AlertDescription>Failed to load features</AlertDescription></Alert>
           : <div className="space-y-3">{features && Object.entries(features).map(([key, enabled]) => (
            <div key={key} className="flex items-center justify-between rounded-lg border border-gray-700 p-3">
              <span className="text-sm font-medium text-gray-200">{key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}</span>
              <div className="flex items-center gap-2">
                <StatusIcon ok={enabled} />
                <span className={`text-xs ${enabled ? 'text-green-400' : 'text-gray-400'}`}>{enabled ? 'Enabled' : 'Disabled'}</span>
              </div>
            </div>
          ))}</div>}
        </CardContent>
      </Card>
    </div>
  )
}
