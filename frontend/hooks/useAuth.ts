'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'
import { getToken, setToken, removeToken, getUser, setUser } from '@/lib/auth'
import type { User, LoginRequest, LoginResponse } from '@/types'

export function useAuth() {
  const router = useRouter()
  const [user, setUserState] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const storedUser = getUser()
    if (storedUser) {
      setUserState(storedUser as User)
    }
    setIsLoading(false)
  }, [])

  const isAuthenticated = typeof window !== 'undefined' ? !!getToken() : false

  const login = useCallback(async (credentials: LoginRequest) => {
    const response = await api.post<LoginResponse>('/api/v1/auth/login', credentials)
    const { access_token, user: userData } = response.data
    setToken(access_token)
    setUser(userData)
    setUserState(userData)
    return userData
  }, [])

  const logout = useCallback(() => {
    removeToken()
    setUserState(null)
    router.push('/login')
  }, [router])

  return { user, isAuthenticated, isLoading, login, logout }
}
