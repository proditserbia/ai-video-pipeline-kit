import axios from 'axios'
import { getToken, removeToken } from './auth'

const apiUrl = process.env.NEXT_PUBLIC_API_URL

if (!apiUrl) {
  console.warn(
    '[api] NEXT_PUBLIC_API_URL is not set. ' +
    'Requests may fail. Set NEXT_PUBLIC_API_URL as a build arg.'
  )
}

const api = axios.create({
  baseURL: apiUrl,
  headers: {
    'Content-Type': 'application/json',
  },
})

api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      removeToken()
      if (typeof window !== 'undefined') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api
