import axios from 'axios'
import { useAuthStore } from '../stores/authStore'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true, // Send cookies with every request
})

// Request interceptor to add auth token (fallback for non-cookie scenarios)
api.interceptors.request.use(
  (config) => {
    const token = useAuthStore.getState().token
    // Only add Authorization header if we have a token and cookies might not be set yet
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor to handle auth errors
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const isAuthEndpoint = error.config?.url?.includes('/auth/')
    
    // Only redirect on 401 if NOT on auth endpoints (login/register)
    // Auth endpoints should show the error message instead
    if (error.response?.status === 401 && !isAuthEndpoint) {
      useAuthStore.getState().logout()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default api


