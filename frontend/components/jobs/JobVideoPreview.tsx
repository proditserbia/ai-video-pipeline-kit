'use client'
import { useRef, useState, useCallback, useEffect } from 'react'
import api from '@/lib/api'

interface JobVideoPreviewProps {
  /** The job ID whose video to preview. */
  jobId: string
  /** Content rendered underneath the video (typically a JobThumbnail). */
  children: React.ReactNode
  /** Extra class names forwarded to the outer wrapper div. */
  className?: string
  /**
   * When false the hover behaviour is disabled entirely (e.g. for jobs that
   * are not yet completed or have no output).  Defaults to true.
   */
  enabled?: boolean
}

/**
 * Wraps any content (usually a thumbnail image) and plays the corresponding
 * job video on mouse-enter, stopping it again on mouse-leave.
 *
 * The video is fetched lazily on the first hover using the authenticated API
 * client (Bearer token injected automatically) and cached as an object URL for
 * the lifetime of the component.  Subsequent hovers play the cached video
 * instantly without a network round-trip.
 *
 * The `<video>` element is always muted and plays inline to comply with
 * browser autoplay policies.
 */
export default function JobVideoPreview({
  jobId,
  children,
  className,
  enabled = true,
}: JobVideoPreviewProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const [isHovered, setIsHovered] = useState(false)
  const [isFetching, setIsFetching] = useState(false)
  // Tracks whether we have already started a fetch so we don't duplicate it.
  const fetchStartedRef = useRef(false)

  // Revoke the object URL when the component unmounts to prevent memory leaks.
  useEffect(() => {
    return () => {
      if (blobUrl) URL.revokeObjectURL(blobUrl)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleMouseEnter = useCallback(() => {
    if (!enabled) return
    setIsHovered(true)

    if (!fetchStartedRef.current) {
      fetchStartedRef.current = true
      setIsFetching(true)
      api
        .get(`jobs/${jobId}/download`, { responseType: 'blob' })
        .then((response) => {
          const url = URL.createObjectURL(
            new Blob([response.data as BlobPart], { type: 'video/mp4' })
          )
          setBlobUrl(url)
        })
        .catch(() => {
          // Video unavailable – reset so the next hover may retry.
          fetchStartedRef.current = false
        })
        .finally(() => {
          setIsFetching(false)
        })
    } else if (blobUrl && videoRef.current) {
      // Video is already cached; play from the beginning.
      videoRef.current.currentTime = 0
      videoRef.current.play().catch(() => {})
    }
  }, [enabled, jobId, blobUrl])

  const handleMouseLeave = useCallback(() => {
    setIsHovered(false)
    if (videoRef.current) {
      videoRef.current.pause()
    }
  }, [])

  // When the blob URL becomes available *while* the user is still hovering,
  // start playback automatically.
  useEffect(() => {
    if (blobUrl && isHovered && videoRef.current) {
      videoRef.current.currentTime = 0
      videoRef.current.play().catch(() => {})
    }
  }, [blobUrl, isHovered])

  return (
    <div
      className={`relative overflow-hidden${className ? ` ${className}` : ''}`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {children}

      {blobUrl && (
        <video
          ref={videoRef}
          src={blobUrl}
          muted
          loop
          playsInline
          aria-hidden="true"
          className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-200 ${
            isHovered ? 'opacity-100' : 'opacity-0 pointer-events-none'
          }`}
        />
      )}

      {isFetching && isHovered && (
        <div
          aria-hidden="true"
          className="absolute inset-0 flex items-center justify-center bg-black/50"
        >
          <span className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent" />
        </div>
      )}
    </div>
  )
}
