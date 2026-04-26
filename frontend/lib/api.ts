import axios from 'axios'
import { getToken, removeToken } from './auth'

const apiUrl = process.env.NEXT_PUBLIC_API_URL

if (!apiUrl) {
  console.warn(
    '[api] NEXT_PUBLIC_API_URL is not set. ' +
    'Falling back to http://localhost:8000/api/v1 for development.'
  )
}

const api = axios.create({
  baseURL: apiUrl || 'http://localhost:8000/api/v1',
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
