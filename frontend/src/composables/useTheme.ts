import { ref } from 'vue'

const STORAGE_KEY = 'statdash-theme'

function systemPrefersDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

function resolveInitial(): 'dark' | 'light' {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'dark' || stored === 'light') return stored
  return systemPrefersDark() ? 'dark' : 'light'
}

function applyTheme(theme: 'dark' | 'light'): void {
  document.documentElement.classList.toggle('dark', theme === 'dark')
}

const theme = ref<'dark' | 'light'>(resolveInitial())
applyTheme(theme.value)

export function useTheme() {
  function toggle(): void {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    applyTheme(theme.value)
    localStorage.setItem(STORAGE_KEY, theme.value)
  }

  return { theme, toggle }
}
