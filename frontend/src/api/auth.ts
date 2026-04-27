import { client } from './client'
import type { User } from '@/types'

export const authApi = {
  async login(email: string, password: string): Promise<void> {
    const form = new FormData()
    form.append('username', email)
    form.append('password', password)
    const response = await fetch('/api/auth/jwt/login', {
      method: 'POST',
      credentials: 'include',
      body: form,
    })
    if (!response.ok) {
      throw new Error('Login failed')
    }
  },

  async logout(): Promise<void> {
    await fetch('/api/auth/jwt/logout', {
      method: 'POST',
      credentials: 'include',
    })
  },

  async me(): Promise<User> {
    return client.request<User>('/users/me')
  },
}
