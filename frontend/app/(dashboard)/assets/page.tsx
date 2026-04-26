'use client'
import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { Card, CardContent } from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { formatFileSize, formatRelativeDate } from '@/lib/utils'
import { Trash2, Upload, File, Music, Video, Image } from 'lucide-react'
import type { Asset, AssetType, PaginatedResponse } from '@/types'

function useAssets(assetType?: string) {
  return useQuery({
    queryKey: ['assets', assetType],
    queryFn: async () => {
      const params = assetType ? `?asset_type=${assetType}` : ''
      const response = await api.get<PaginatedResponse<Asset>>(`assets${params}`)
      return response.data
    },
  })
}

function useDeleteAsset() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => { await api.delete(`assets/${id}`) },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['assets'] }),
  })
}

function useUploadAsset() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (formData: FormData) => {
      const response = await api.post<Asset>('assets/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
      return response.data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['assets'] }),
  })
}

function getAssetIcon(type: AssetType) {
  const icons: Record<AssetType, React.ElementType> = { video: Video, audio: Music, image: Image, script: File, other: File }
  const Icon = icons[type] || File
  return <Icon className="h-5 w-5" />
}

export default function AssetsPage() {
  const [typeFilter, setTypeFilter] = useState<string>('')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { data: assets, isLoading, error } = useAssets(typeFilter || undefined)
  const deleteAsset = useDeleteAsset()
  const uploadAsset = useUploadAsset()
  const [uploadError, setUploadError] = useState<string | null>(null)

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    try { setUploadError(null); await uploadAsset.mutateAsync(formData) }
    catch { setUploadError('Failed to upload file') }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Assets</h1>
        <Button onClick={() => fileInputRef.current?.click()} isLoading={uploadAsset.isPending}>
          <Upload className="mr-2 h-4 w-4" />Upload Asset
        </Button>
        <input ref={fileInputRef} type="file" className="hidden" onChange={handleUpload} />
      </div>
      {uploadError && <Alert variant="destructive"><AlertDescription>{uploadError}</AlertDescription></Alert>}
      <Select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="w-40">
        <option value="">All Types</option>
        <option value="video">Video</option>
        <option value="audio">Audio</option>
        <option value="image">Image</option>
        <option value="script">Script</option>
        <option value="other">Other</option>
      </Select>
      {isLoading ? <div className="flex justify-center py-12"><Spinner /></div>
       : error ? <Alert variant="destructive"><AlertDescription>Failed to load assets</AlertDescription></Alert>
       : assets?.items?.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-gray-400">
          <File className="mb-3 h-12 w-12 opacity-30" /><p>No assets yet.</p>
        </div>
       ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {assets?.items?.map((asset) => (
            <Card key={asset.id}>
              <CardContent className="p-4">
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-gray-700 text-gray-400">
                  {getAssetIcon(asset.asset_type)}
                </div>
                <p className="truncate text-sm font-medium text-white">{asset.name}</p>
                <p className="mt-1 text-xs text-gray-400">{asset.asset_type} · {formatFileSize(asset.file_size)}</p>
                <p className="text-xs text-gray-500">{formatRelativeDate(asset.created_at)}</p>
                <Button size="sm" variant="destructive" className="mt-3 w-full" onClick={() => deleteAsset.mutate(asset.id)} isLoading={deleteAsset.isPending}>
                  <Trash2 className="mr-1 h-3 w-3" />Delete
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
       )}
    </div>
  )
}
