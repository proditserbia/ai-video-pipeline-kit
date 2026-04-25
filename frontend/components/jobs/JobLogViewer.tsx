'use client'
import { useEffect, useRef } from 'react'

interface JobLogViewerProps {
  logs: string[]
}

export default function JobLogViewer({ logs }: JobLogViewerProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  return (
    <div className="h-80 overflow-y-auto rounded-lg border border-gray-700 bg-black p-4">
      <pre className="font-mono text-xs text-green-400">
        {logs.length === 0 ? (
          <span className="text-gray-500">No logs available</span>
        ) : (
          logs.map((log, i) => (
            <div key={i} className="py-0.5">
              {log}
            </div>
          ))
        )}
      </pre>
      <div ref={bottomRef} />
    </div>
  )
}
