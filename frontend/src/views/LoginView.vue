<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useTheme } from '@/composables/useTheme'

const { theme, toggle: toggleTheme } = useTheme()

const email = ref('')
const password = ref('')
const error = ref<string | null>(null)
const loading = ref(false)
const router = useRouter()
const auth = useAuthStore()

async function handleLogin() {
  error.value = null
  loading.value = true
  try {
    await auth.login(email.value, password.value)
    await router.push({ name: 'dashboard' })
  } catch {
    error.value = 'Invalid credentials'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-background flex items-center justify-center">
    <button
      class="fixed top-3 right-4 text-sm text-muted-foreground hover:text-foreground transition-colors"
      :title="theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'"
      @click="toggleTheme"
    >
      {{ theme === 'dark' ? '☀' : '☾' }}
    </button>
    <div class="w-full max-w-sm space-y-6 p-8 border border-border rounded-lg bg-card shadow-sm">
      <div>
        <h1 class="text-2xl font-bold text-foreground">StatDash</h1>
        <p class="text-sm text-muted-foreground mt-1">Infrastructure monitoring dashboard</p>
      </div>

      <form class="space-y-4" @submit.prevent="handleLogin">
        <div class="space-y-1">
          <label class="text-sm font-medium text-foreground" for="email">Email</label>
          <input
            id="email"
            v-model="email"
            type="email"
            required
            autocomplete="email"
            class="w-full px-3 py-2 border border-input rounded-md bg-background text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>

        <div class="space-y-1">
          <label class="text-sm font-medium text-foreground" for="password">Password</label>
          <input
            id="password"
            v-model="password"
            type="password"
            required
            autocomplete="current-password"
            class="w-full px-3 py-2 border border-input rounded-md bg-background text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>

        <p v-if="error" class="text-sm text-destructive">{{ error }}</p>

        <button
          type="submit"
          :disabled="loading"
          class="w-full py-2 px-4 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {{ loading ? 'Signing in...' : 'Sign in' }}
        </button>
      </form>
    </div>
  </div>
</template>
