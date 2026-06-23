import { client } from './client'
import type { User } from '@/types'

export interface SsoConfig {
  enabled: boolean
  button_label: string | null
}

export const authApi = {
  async fetchSsoConfig(): Promise<SsoConfig> {
    return client.request<SsoConfig>('/auth/sso/config')
  },

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

  async updateMe(data: Partial<Pick<User, 'ssh_command_prefix'>>): Promise<User> {
    return client.request<User>('/users/me', {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  },
}
