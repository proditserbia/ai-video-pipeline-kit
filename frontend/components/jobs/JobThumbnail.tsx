'use client'
import { useState, useEffect } from 'react'
import api from '@/lib/api'

interface JobThumbnailProps {
  jobId: string
  className?: string
  alt?: string
}

/**
 * Fetches a job thumbnail via the authenticated API and renders it as an
 * <img> element.  A plain <img src={thumbnailUrl}> cannot work here because
 * the /jobs/{id}/thumbnail endpoint requires a Bearer token; this component
 * uses the shared axios client (which injects the token) and converts the
 * response blob into an object URL that the browser can render.
 *
 * The object URL is revoked when the component unmounts to prevent memory leaks.
 */
export default function JobThumbnail({ jobId, className, alt = 'Video thumbnail' }: JobThumbnailProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null)

  useEffect(() => {
    let objectUrl: string | null = null

    api
      .get(`jobs/${jobId}/thumbnail`, { responseType: 'blob' })
      .then((response) => {
        objectUrl = URL.createObjectURL(response.data as Blob)
        setBlobUrl(objectUrl)
      })
      .catch(() => {
        // Thumbnail unavailable – render nothing.
        setBlobUrl(null)
      })

    return () => {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl)
      }
    }
  }, [jobId])

  if (!blobUrl) return null

  // eslint-disable-next-line @next/next/no-img-element
  return <img src={blobUrl} alt={alt} className={className} />
}
