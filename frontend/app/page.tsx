'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { getToken } from '@/lib/auth'

export default function Home() {
  const router = useRouter()
  useEffect(() => {
    if (getToken()) {
      router.replace('/dashboard')
    } else {
      router.replace('/login')
    }
  }, [router])
  return (
    <div className="flex h-screen items-center justify-center bg-gray-900">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-600 border-t-blue-500" />
    </div>
  )
}
