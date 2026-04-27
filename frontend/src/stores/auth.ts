import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { User } from '@/types'
import { authApi } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const initialized = ref(false)

  async function initialize(): Promise<void> {
    if (initialized.value) return
    try {
      user.value = await authApi.me()
    } catch {
      user.value = null
    }
    initialized.value = true
  }

  async function login(email: string, password: string): Promise<void> {
    await authApi.login(email, password)
    user.value = await authApi.me()
  }

  async function logout(): Promise<void> {
    await authApi.logout()
    user.value = null
    initialized.value = false
  }

  return { user, initialize, login, logout }
})
