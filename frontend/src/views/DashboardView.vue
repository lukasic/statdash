<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, type Ref } from 'vue'

const now = ref(Date.now())
let tickInterval: ReturnType<typeof setInterval> | null = null

function formatSince(iso: string): string {
  return new Date(iso).toLocaleString('sk-SK', {
    day: 'numeric',
    month: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatChecked(iso: string): string {
  return new Date(iso).toLocaleString('sk-SK', {
    day: 'numeric',
    month: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function firstLine(output: string): string {
  const line = output.split('\n')[0]
  return line.length > 100 ? line.slice(0, 100) + '…' : line
}

function formatDuration(iso: string): string {
  const totalSeconds = Math.floor((now.value - new Date(iso).getTime()) / 1000)
  const s = totalSeconds % 60
  const totalMinutes = Math.floor(totalSeconds / 60)
  const m = totalMinutes % 60
  const totalHours = Math.floor(totalMinutes / 60)
  const h = totalHours % 24
  const d = Math.floor(totalHours / 24)
  if (d > 0) return `${d}d ${h}h ${m}m`
  if (h > 0) return `${h}h ${m}m ${s}s`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useTheme } from '@/composables/useTheme'
import type { DashboardData, Note } from '@/types'
import { listNotes, createNote, updateNote, deleteNote } from '@/api/notes'
import { triggerRecheck, removeAck, removeDowntime, acknowledge, scheduleDowntime } from '@/api/actions'

const { theme, toggle: toggleTheme } = useTheme()

// ── High contrast ─────────────────────────────────────────────────────────────

const highContrast = ref(localStorage.getItem('statdash-high-contrast') === '1')

function applyHighContrast(val: boolean): void {
  document.documentElement.classList.toggle('high-contrast', val)
}

applyHighContrast(highContrast.value)

function toggleHighContrast(): void {
  highContrast.value = !highContrast.value
  localStorage.setItem('statdash-high-contrast', highContrast.value ? '1' : '0')
  applyHighContrast(highContrast.value)
}

// ── Filter mode ───────────────────────────────────────────────────────────────

type FilterMode = 'active' | 'all' | 'acknowledged' | 'in_downtime'
const FILTER_MODE_KEY = 'statdash-filter-mode'

function resolveFilterMode(): FilterMode {
  const stored = localStorage.getItem(FILTER_MODE_KEY)
  if (stored === 'all' || stored === 'acknowledged' || stored === 'in_downtime') return stored
  return 'active'
}

const filterMode = ref<FilterMode>(resolveFilterMode())

function setFilterMode(mode: FilterMode): void {
  filterMode.value = mode
  localStorage.setItem(FILTER_MODE_KEY, mode)
}

import type { Check } from '@/types'

function applyFilter(checks: Check[]): Check[] {
  if (filterMode.value === 'all') return checks
  if (filterMode.value === 'acknowledged') return checks.filter(c => c.acknowledged)
  if (filterMode.value === 'in_downtime') return checks.filter(c => c.in_downtime)
  // 'active': neither acknowledged nor in downtime
  return checks.filter(c => !c.acknowledged && !c.in_downtime)
}

// ── View mode ─────────────────────────────────────────────────────────────────

type ViewMode = 'cards' | 'table'
const VIEW_MODE_KEY = 'statdash-view-mode'

function resolveViewMode(): ViewMode {
  const stored = localStorage.getItem(VIEW_MODE_KEY)
  return stored === 'table' ? 'table' : 'cards'
}

const viewMode = ref<ViewMode>(resolveViewMode())

function toggleViewMode(): void {
  viewMode.value = viewMode.value === 'cards' ? 'table' : 'cards'
  localStorage.setItem(VIEW_MODE_KEY, viewMode.value)
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

const auth = useAuthStore()
const router = useRouter()
const data = ref<DashboardData | null>(null)
const connected = ref(false)

let ws: WebSocket | null = null
let reconnectTimeout: ReturnType<typeof setTimeout> | null = null

function connect() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${protocol}//${window.location.host}/api/ws`)
  ws.onopen = () => { connected.value = true }
  ws.onmessage = (event: MessageEvent) => {
    data.value = JSON.parse(event.data as string) as DashboardData
  }
  ws.onclose = () => {
    connected.value = false
    reconnectTimeout = setTimeout(connect, 3000)
  }
}

async function handleLogout() {
  await auth.logout()
  await router.push({ name: 'login' })
}

onMounted(() => {
  connect()
  tickInterval = setInterval(() => { now.value = Date.now() }, 1000)
  window.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  if (reconnectTimeout) clearTimeout(reconnectTimeout)
  if (tickInterval) clearInterval(tickInterval)
  ws?.close()
  window.removeEventListener('keydown', onKeydown)
})

// ── Notes ─────────────────────────────────────────────────────────────────────

const openNotes = ref<Set<string>>(new Set())
const notesCache = ref<Record<string, Note[]>>({})
const newNoteContent = ref<Record<string, string>>({})
const noteGeneral = ref<Record<string, boolean>>({})
const loadingNotes = ref<Set<string>>(new Set())

async function toggleNotes(checkId: string, source: string, checkName: string, host: string): Promise<void> {
  if (openNotes.value.has(checkId)) {
    openNotes.value.delete(checkId)
    return
  }
  openNotes.value.add(checkId)
  await loadNotes(checkId, source, checkName, host)
}

async function loadNotes(checkId: string, source: string, checkName: string, host: string): Promise<void> {
  loadingNotes.value.add(checkId)
  try {
    notesCache.value[checkId] = await listNotes(source, checkName, host)
  } finally {
    loadingNotes.value.delete(checkId)
  }
}

async function submitNote(checkId: string, source: string, checkName: string, host: string): Promise<void> {
  const content = (newNoteContent.value[checkId] ?? '').trim()
  if (!content) return
  const effectiveHost = noteGeneral.value[checkId] ? null : host
  await createNote({ source, check_name: checkName, host: effectiveHost, content })
  newNoteContent.value[checkId] = ''
  await loadNotes(checkId, source, checkName, host)
}

async function toggleResolved(note: Note, checkId: string, source: string, checkName: string, host: string): Promise<void> {
  await updateNote(note.id, { resolved: !note.resolved })
  await loadNotes(checkId, source, checkName, host)
}

async function removeNote(noteId: string, checkId: string, source: string, checkName: string, host: string): Promise<void> {
  await deleteNote(noteId)
  await loadNotes(checkId, source, checkName, host)
}

// ── Actions ───────────────────────────────────────────────────────────────────

const icinga2Sources = computed<Set<string>>(() => {
  const s = new Set<string>()
  for (const src of data.value?.sources ?? []) {
    if (src.type === 'icinga2') s.add(src.name)
  }
  return s
})

const prometheusSources = computed<Set<string>>(() => {
  const s = new Set<string>()
  for (const src of data.value?.sources ?? []) {
    if (src.type === 'prometheus') s.add(src.name)
  }
  return s
})

const urlSources = computed<Set<string>>(() => {
  const s = new Set<string>()
  for (const src of data.value?.sources ?? []) {
    if (src.type === 'nodeping' || src.type === 'uptimekuma') s.add(src.name)
  }
  return s
})

type ActionState = 'idle' | 'loading' | 'done' | 'error'
const recheckState = ref<Map<string, ActionState>>(new Map())
const removeAckState = ref<Map<string, ActionState>>(new Map())
const removeDowntimeState = ref<Map<string, ActionState>>(new Map())

function makeActionHandler(
  stateMap: Ref<Map<string, ActionState>>,
  fn: (source: string, checkId: string) => Promise<void>,
) {
  return async (source: string, checkId: string): Promise<void> => {
    stateMap.value.set(checkId, 'loading')
    try {
      await fn(source, checkId)
      stateMap.value.set(checkId, 'done')
      setTimeout(() => stateMap.value.set(checkId, 'idle'), 2000)
    } catch {
      stateMap.value.set(checkId, 'error')
      setTimeout(() => stateMap.value.set(checkId, 'idle'), 3000)
    }
  }
}

const doRecheck = makeActionHandler(recheckState, triggerRecheck)
const doRemoveAck = makeActionHandler(removeAckState, removeAck)
const doRemoveDowntime = makeActionHandler(removeDowntimeState, removeDowntime)

// ── Action modal (ack / downtime) ─────────────────────────────────────────────

type ActionModalType = 'ack' | 'downtime'

interface ActionModalState {
  type: ActionModalType
  source: string
  checkId: string
  checkName: string
}

const actionModal = ref<ActionModalState | null>(null)
const actionComment = ref('')
const actionExpiryMode = ref<'slider' | 'datetime'>('slider')
const actionExpiryHours = ref(2)
const actionExpiryDatetime = ref('')
const actionSubmitting = ref(false)

function openActionModal(type: ActionModalType, source: string, checkId: string, checkName: string): void {
  actionModal.value = { type, source, checkId, checkName }
  actionComment.value = ''
  actionExpiryMode.value = 'slider'
  actionExpiryHours.value = 2
  const def = new Date(Date.now() + 2 * 60 * 60 * 1000)
  actionExpiryDatetime.value = new Date(def.getTime() - def.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16)
}

function closeActionModal(): void {
  if (actionSubmitting.value) return
  actionModal.value = null
}

function resolveExpiryIso(): string {
  if (actionExpiryMode.value === 'slider') {
    return new Date(Date.now() + actionExpiryHours.value * 60 * 60 * 1000).toISOString()
  }
  return new Date(actionExpiryDatetime.value).toISOString()
}

async function submitActionModal(): Promise<void> {
  if (!actionModal.value || !actionComment.value.trim()) return
  actionSubmitting.value = true
  try {
    const { type, source, checkId } = actionModal.value
    const expiry = resolveExpiryIso()
    if (type === 'ack') {
      await acknowledge(source, checkId, actionComment.value.trim(), expiry)
    } else {
      await scheduleDowntime(source, checkId, actionComment.value.trim(), expiry)
    }
    actionModal.value = null
  } finally {
    actionSubmitting.value = false
  }
}

// ── SSH copy ─────────────────────────────────────────────────────────────────

const copiedHost = ref<string | null>(null)

async function copySSH(host: string): Promise<void> {
  const prefix = auth.user?.ssh_command_prefix ?? 'ssh'
  await navigator.clipboard.writeText(`${prefix} ${host}`)
  copiedHost.value = host
  setTimeout(() => { copiedHost.value = null }, 2000)
}

// ── SSH settings modal ───────────────────────────────────────────────────────

const sshSettingsOpen = ref(false)
const sshPrefixInput = ref('')
const sshSettingsSaving = ref(false)

function openSshSettings(): void {
  sshPrefixInput.value = auth.user?.ssh_command_prefix ?? 'ssh'
  sshSettingsOpen.value = true
}

function closeSshSettings(): void {
  sshSettingsOpen.value = false
}

async function saveSshSettings(): Promise<void> {
  const trimmed = sshPrefixInput.value.trim()
  if (!trimmed) return
  sshSettingsSaving.value = true
  try {
    await auth.updateSshCommandPrefix(trimmed)
    sshSettingsOpen.value = false
  } finally {
    sshSettingsSaving.value = false
  }
}

// ── Output modal ──────────────────────────────────────────────────────────────

const outputModal = ref<{ name: string; output: string } | null>(null)

function openOutputModal(name: string, output: string): void {
  outputModal.value = { name, output }
}

function closeOutputModal(): void {
  outputModal.value = null
}

function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Escape') { closeOutputModal(); closeActionModal(); closeSshSettings() }
}
</script>

<template>
  <div class="min-h-screen bg-background">
    <header class="border-b border-border px-6 py-3 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <h1 class="text-base font-semibold text-foreground">StatDash</h1>
        <span
          class="inline-block w-2 h-2 rounded-full"
          :class="connected ? 'bg-green-500' : 'bg-red-500'"
          :title="connected ? 'Connected' : 'Disconnected'"
        />
      </div>
      <div class="flex items-center gap-4">
        <span class="text-sm text-muted-foreground">{{ auth.user?.email }}</span>
        <!-- High contrast toggle -->
        <button
          class="text-sm transition-colors"
          :class="highContrast ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'"
          :title="highContrast ? 'High contrast on' : 'High contrast off'"
          @click="toggleHighContrast"
        >◑</button>
        <!-- View mode toggle -->
        <button
          class="text-sm text-muted-foreground hover:text-foreground transition-colors"
          :title="viewMode === 'cards' ? 'Switch to table view' : 'Switch to card view'"
          @click="toggleViewMode"
        >
          {{ viewMode === 'cards' ? '☰' : '⊞' }}
        </button>
        <button
          class="text-sm text-muted-foreground hover:text-foreground transition-colors"
          :title="theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'"
          @click="toggleTheme"
        >
          {{ theme === 'dark' ? '☀' : '☾' }}
        </button>
        <button
          class="text-sm text-muted-foreground hover:text-foreground transition-colors"
          :title="`SSH prefix: ${auth.user?.ssh_command_prefix ?? 'ssh'}`"
          @click="openSshSettings"
        >
          SSH
        </button>
        <button
          class="text-sm text-muted-foreground hover:text-foreground transition-colors"
          @click="handleLogout"
        >
          Logout
        </button>
      </div>
    </header>

    <main class="p-6">
      <div v-if="!data" class="text-sm text-muted-foreground">Connecting to data stream...</div>

      <div v-else class="space-y-8">
        <div
          v-if="data.sources.some(s => !s.available)"
          class="flex flex-col gap-1 p-3 rounded-md border border-yellow-500/30 bg-yellow-500/5"
        >
          <p
            v-for="source in data.sources.filter(s => !s.available)"
            :key="source.name"
            class="text-sm text-yellow-700"
          >
            Source <span class="font-medium">{{ source.name }}</span> is unavailable.
          </p>
        </div>

        <!-- Filter tiles -->
        <div class="flex items-center gap-1.5">
          <button
            v-for="f in ([
              { mode: 'active', label: 'Active' },
              { mode: 'acknowledged', label: 'Acknowledged' },
              { mode: 'in_downtime', label: 'In downtime' },
              { mode: 'all', label: 'All' },
            ] as const)"
            :key="f.mode"
            class="px-3 py-1 rounded text-xs font-medium border transition-colors"
            :class="filterMode === f.mode
              ? 'bg-foreground text-background border-foreground'
              : 'text-muted-foreground border-border hover:border-foreground/40 hover:text-foreground'"
            @click="setFilterMode(f.mode)"
          >
            {{ f.label }}
          </button>
        </div>

        <div
          v-for="section in data.sections"
          :key="section.name"
          class="space-y-2"
        >
          <!-- Section header -->
          <div class="flex items-center justify-between border-b border-border pb-2">
            <h2 class="text-sm font-semibold text-foreground uppercase tracking-wide">
              {{ section.name }}
            </h2>
            <span class="text-xs text-muted-foreground">{{ applyFilter(section.checks).length }} issues</span>
          </div>

          <p v-if="applyFilter(section.checks).length === 0" class="text-sm text-muted-foreground">
            All checks OK
          </p>

          <!-- ── CARDS ── -->
          <div v-else-if="viewMode === 'cards'" class="space-y-2">
            <div
              v-for="check in applyFilter(section.checks)"
              :key="check.id"
              class="rounded-md border"
              :class="{
                'border-yellow-500/40 bg-yellow-500/5': check.status === 'warning',
                'border-red-500/40 bg-red-500/5': check.status === 'critical',
                'border-gray-400/40 bg-gray-500/5': check.status === 'unknown',
              }"
            >
              <div class="p-3">
                <div class="flex items-center justify-between gap-4">
                  <div class="min-w-0">
                    <span class="font-medium text-sm text-foreground">{{ check.name }}</span>
                    <a
                      v-if="urlSources.has(check.source)"
                      :href="check.host"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="text-xs text-muted-foreground ml-2 hover:text-foreground transition-colors"
                      :title="`Open: ${check.host}`"
                      @click.stop
                    >{{ check.host }}</a>
                    <button
                      v-else
                      class="text-xs text-muted-foreground ml-2 transition-colors"
                      :class="copiedHost === check.host ? 'text-green-600' : 'hover:text-foreground'"
                      :title="copiedHost === check.host ? 'Copied!' : `Copy: ssh ${check.host}`"
                      @click.stop="copySSH(check.host)"
                    >{{ check.host }}</button>
                  </div>
                  <div class="shrink-0 flex items-center gap-2">
                    <a
                      v-if="check.url"
                      :href="check.url"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="text-xs text-muted-foreground hover:underline"
                      @click.stop
                    >{{ check.source }}</a>
                    <span v-else class="text-xs text-muted-foreground">{{ check.source }}</span>
                    <span
                      class="text-xs font-semibold uppercase px-2 py-0.5 rounded"
                      :class="{
                        'bg-yellow-500/20 text-yellow-700': check.status === 'warning',
                        'bg-red-500/20 text-red-700': check.status === 'critical',
                        'bg-gray-500/20 text-gray-600': check.status === 'unknown',
                      }"
                    >
                      {{ check.status }}
                    </span>
                  </div>
                </div>
                <div v-if="check.output" class="flex items-center gap-1 mt-1">
                  <p class="text-xs text-muted-foreground flex-1">{{ firstLine(check.output) }}</p>
                  <button
                    class="shrink-0 text-xs text-muted-foreground/50 hover:text-foreground transition-colors"
                    title="Show full output"
                    @click="openOutputModal(check.name, check.output)"
                  >⤢</button>
                </div>
                <div
                  v-if="check.ack_comment || (check.acknowledged && icinga2Sources.has(check.source))"
                  class="flex items-start gap-1 text-xs font-bold italic text-muted-foreground mt-0.5"
                >
                  <span class="flex-1">
                    {{ check.ack_comment || 'Acknowledged' }}
                    <span v-if="check.ack_expiry" class="font-normal not-italic"> · expires {{ formatChecked(check.ack_expiry) }}</span>
                  </span>
                  <button
                    v-if="icinga2Sources.has(check.source)"
                    class="shrink-0 font-normal not-italic transition-colors"
                    :class="removeAckState.get(check.id) === 'loading' ? 'text-muted-foreground/30 cursor-wait' : 'text-muted-foreground/50 hover:text-destructive'"
                    :disabled="removeAckState.get(check.id) === 'loading'"
                    title="Remove acknowledgement"
                    @click="doRemoveAck(check.source, check.id)"
                  >{{ removeAckState.get(check.id) === 'loading' ? '…' : removeAckState.get(check.id) === 'done' ? '✓' : '×' }}</button>
                </div>
                <div
                  v-if="check.downtime_comment || (check.in_downtime && (icinga2Sources.has(check.source) || prometheusSources.has(check.source)))"
                  class="flex items-start gap-1 text-xs font-bold italic text-muted-foreground mt-0.5"
                >
                  <span class="flex-1">
                    {{ check.downtime_comment || 'In downtime' }}
                    <span v-if="check.downtime_expiry" class="font-normal not-italic"> · ends {{ formatChecked(check.downtime_expiry) }}</span>
                  </span>
                  <button
                    v-if="icinga2Sources.has(check.source) || prometheusSources.has(check.source)"
                    class="shrink-0 font-normal not-italic transition-colors"
                    :class="removeDowntimeState.get(check.id) === 'loading' ? 'text-muted-foreground/30 cursor-wait' : 'text-muted-foreground/50 hover:text-destructive'"
                    :disabled="removeDowntimeState.get(check.id) === 'loading'"
                    :title="prometheusSources.has(check.source) ? 'Remove silence' : 'Remove downtime'"
                    @click="doRemoveDowntime(check.source, check.id)"
                  >{{ removeDowntimeState.get(check.id) === 'loading' ? '…' : removeDowntimeState.get(check.id) === 'done' ? '✓' : '×' }}</button>
                </div>
                <div class="text-xs text-muted-foreground/70 mt-0.5 space-y-0.5">
                  <p v-if="check.since">od {{ formatSince(check.since) }} · {{ formatDuration(check.since) }}</p>
                  <p v-if="check.last_checked">checked {{ formatChecked(check.last_checked) }}</p>
                </div>
                <div class="mt-2 flex items-center gap-3">
                  <button
                    class="text-xs text-muted-foreground hover:text-foreground transition-colors"
                    @click="toggleNotes(check.id, check.source, check.name, check.host)"
                  >
                    {{ openNotes.has(check.id) ? 'Hide notes' : 'Notes' }}
                  </button>
                  <button
                    v-if="icinga2Sources.has(check.source)"
                    class="text-xs transition-colors"
                    :class="{
                      'text-muted-foreground hover:text-foreground': recheckState.get(check.id) === 'idle' || !recheckState.has(check.id),
                      'text-muted-foreground/50 cursor-wait': recheckState.get(check.id) === 'loading',
                      'text-green-600': recheckState.get(check.id) === 'done',
                      'text-red-500': recheckState.get(check.id) === 'error',
                    }"
                    :disabled="recheckState.get(check.id) === 'loading'"
                    @click="doRecheck(check.source, check.id)"
                  >
                    {{
                      recheckState.get(check.id) === 'loading' ? 'Checking…'
                      : recheckState.get(check.id) === 'done' ? '✓ Rechecked'
                      : recheckState.get(check.id) === 'error' ? '✗ Failed'
                      : 'Recheck'
                    }}
                  </button>
                  <button
                    v-if="icinga2Sources.has(check.source) && !check.acknowledged"
                    class="text-xs text-muted-foreground hover:text-foreground transition-colors"
                    @click="openActionModal('ack', check.source, check.id, check.name)"
                  >Ack</button>
                  <button
                    v-if="(icinga2Sources.has(check.source) || prometheusSources.has(check.source)) && !check.in_downtime"
                    class="text-xs text-muted-foreground hover:text-foreground transition-colors"
                    @click="openActionModal('downtime', check.source, check.id, check.name)"
                  >{{ prometheusSources.has(check.source) ? 'Silence' : 'Downtime' }}</button>
                </div>
              </div>

              <!-- Notes panel (cards) -->
              <div
                v-if="openNotes.has(check.id)"
                class="border-t border-border/50 px-3 pb-3 pt-2 space-y-2"
              >
                <template v-if="loadingNotes.has(check.id)">
                  <p class="text-xs text-muted-foreground">Loading…</p>
                </template>
                <template v-else>
                  <p
                    v-if="(notesCache[check.id] ?? []).length === 0"
                    class="text-xs text-muted-foreground"
                  >
                    No notes yet.
                  </p>
                  <div
                    v-for="note in notesCache[check.id] ?? []"
                    :key="note.id"
                    class="flex items-start gap-2"
                  >
                    <div class="flex-1 min-w-0">
                      <p class="text-xs" :class="note.resolved ? 'line-through text-muted-foreground/50' : 'text-foreground'">
                        {{ note.content }}
                      </p>
                      <p class="text-xs text-muted-foreground/50 mt-0.5">
                        {{ note.host ? note.host : 'general' }} · {{ new Date(note.created_at).toLocaleString('sk-SK') }} · {{ note.author }}
                      </p>
                    </div>
                    <div class="shrink-0 flex gap-1">
                      <button
                        class="text-xs text-muted-foreground hover:text-foreground transition-colors"
                        :title="note.resolved ? 'Reopen' : 'Mark resolved'"
                        @click="toggleResolved(note, check.id, check.source, check.name, check.host)"
                      >{{ note.resolved ? '↩' : '✓' }}</button>
                      <button
                        class="text-xs text-muted-foreground hover:text-red-500 transition-colors"
                        title="Delete"
                        @click="removeNote(note.id, check.id, check.source, check.name, check.host)"
                      >×</button>
                    </div>
                  </div>
                  <label class="flex items-center gap-1.5 text-xs text-muted-foreground mt-1 cursor-pointer select-none">
                    <input
                      v-model="noteGeneral[check.id]"
                      type="checkbox"
                      class="accent-foreground"
                    />
                    General ({{ check.source }} · {{ check.name }})
                  </label>
                  <div class="flex gap-2 mt-1">
                    <input
                      v-model="newNoteContent[check.id]"
                      type="text"
                      placeholder="Add a note…"
                      class="flex-1 text-xs bg-background border border-border rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-ring"
                      @keydown.enter="submitNote(check.id, check.source, check.name, check.host)"
                    />
                    <button
                      class="text-xs px-2 py-1 rounded bg-muted hover:bg-muted/80 text-foreground transition-colors"
                      @click="submitNote(check.id, check.source, check.name, check.host)"
                    >Add</button>
                  </div>
                </template>
              </div>
            </div>
          </div>

          <!-- ── TABLE ── -->
          <template v-else>
            <table class="w-full text-xs border-collapse">
              <thead>
                <tr class="text-muted-foreground border-b border-border">
                  <th class="text-left font-medium py-1 pr-3 w-20">Status</th>
                  <th class="text-left font-medium py-1 pr-3">Name</th>
                  <th class="text-left font-medium py-1 pr-3">Host</th>
                  <th class="text-left font-medium py-1 pr-3">Source</th>
                  <th class="text-left font-medium py-1 pr-3 w-28">Duration</th>
                  <th class="text-left font-medium py-1 pr-3 w-36">Checked</th>
                  <th class="py-1 w-16"></th>
                </tr>
              </thead>
              <tbody>
                <template v-for="check in applyFilter(section.checks)" :key="check.id">
                  <tr
                    class="border-b border-border/40 hover:bg-muted/30 transition-colors cursor-default"
                    :class="{
                      'bg-yellow-500/5': check.status === 'warning',
                      'bg-red-500/5': check.status === 'critical',
                      'bg-gray-500/5': check.status === 'unknown',
                    }"
                    @dblclick="toggleNotes(check.id, check.source, check.name, check.host)"
                  >
                    <td class="py-1.5 pr-3">
                      <span
                        class="font-semibold uppercase px-1.5 py-0.5 rounded"
                        :class="{
                          'bg-yellow-500/20 text-yellow-700': check.status === 'warning',
                          'bg-red-500/20 text-red-700': check.status === 'critical',
                          'bg-gray-500/20 text-gray-600': check.status === 'unknown',
                        }"
                      >{{ check.status }}</span>
                    </td>
                    <td class="py-1.5 pr-3">
                      <div class="flex items-baseline gap-1">
                        <span class="font-medium text-foreground">{{ check.name }}</span>
                        <span
                          v-if="check.output"
                          class="text-xs text-muted-foreground/60"
                        >— {{ firstLine(check.output) }}</span>
                        <button
                          v-if="check.output"
                          class="text-xs text-muted-foreground/50 hover:text-foreground transition-colors shrink-0"
                          title="Show full output"
                          @click="openOutputModal(check.name, check.output)"
                        >⤢</button>
                      </div>
                      <div
                        v-if="check.ack_comment || (check.acknowledged && icinga2Sources.has(check.source))"
                        class="flex items-start gap-1 text-xs font-bold italic text-muted-foreground leading-tight"
                      >
                        <span class="flex-1">
                          {{ check.ack_comment || 'Acknowledged' }}
                          <span v-if="check.ack_expiry" class="font-normal not-italic"> · expires {{ formatChecked(check.ack_expiry) }}</span>
                        </span>
                        <button
                          v-if="icinga2Sources.has(check.source)"
                          class="shrink-0 font-normal not-italic transition-colors"
                          :class="removeAckState.get(check.id) === 'loading' ? 'text-muted-foreground/30 cursor-wait' : 'text-muted-foreground/50 hover:text-destructive'"
                          :disabled="removeAckState.get(check.id) === 'loading'"
                          title="Remove acknowledgement"
                          @click="doRemoveAck(check.source, check.id)"
                        >{{ removeAckState.get(check.id) === 'loading' ? '…' : removeAckState.get(check.id) === 'done' ? '✓' : '×' }}</button>
                      </div>
                      <div
                        v-if="check.downtime_comment || (check.in_downtime && (icinga2Sources.has(check.source) || prometheusSources.has(check.source)))"
                        class="flex items-start gap-1 text-xs font-bold italic text-muted-foreground leading-tight"
                      >
                        <span class="flex-1">
                          {{ check.downtime_comment || 'In downtime' }}
                          <span v-if="check.downtime_expiry" class="font-normal not-italic"> · ends {{ formatChecked(check.downtime_expiry) }}</span>
                        </span>
                        <button
                          v-if="icinga2Sources.has(check.source) || prometheusSources.has(check.source)"
                          class="shrink-0 font-normal not-italic transition-colors"
                          :class="removeDowntimeState.get(check.id) === 'loading' ? 'text-muted-foreground/30 cursor-wait' : 'text-muted-foreground/50 hover:text-destructive'"
                          :disabled="removeDowntimeState.get(check.id) === 'loading'"
                          :title="prometheusSources.has(check.source) ? 'Remove silence' : 'Remove downtime'"
                          @click="doRemoveDowntime(check.source, check.id)"
                        >{{ removeDowntimeState.get(check.id) === 'loading' ? '…' : removeDowntimeState.get(check.id) === 'done' ? '✓' : '×' }}</button>
                      </div>
                    </td>
                    <td class="py-1.5 pr-3 whitespace-nowrap">
                      <a
                        v-if="urlSources.has(check.source)"
                        :href="check.host"
                        target="_blank"
                        rel="noopener noreferrer"
                        class="text-muted-foreground hover:text-foreground transition-colors"
                        :title="`Open: ${check.host}`"
                      >{{ check.host }}</a>
                      <button
                        v-else
                        class="transition-colors"
                        :class="copiedHost === check.host ? 'text-green-600' : 'text-muted-foreground hover:text-foreground'"
                        :title="copiedHost === check.host ? 'Copied!' : `Copy: ssh ${check.host}`"
                        @click="copySSH(check.host)"
                      >{{ check.host }}</button>
                    </td>
                    <td class="py-1.5 pr-3 text-muted-foreground whitespace-nowrap">
                      <a
                        v-if="check.url"
                        :href="check.url"
                        target="_blank"
                        rel="noopener noreferrer"
                        class="hover:underline"
                      >{{ check.source }}</a>
                      <template v-else>{{ check.source }}</template>
                    </td>
                    <td class="py-1.5 pr-3 text-muted-foreground whitespace-nowrap font-mono tabular-nums" :title="check.since ? formatSince(check.since) : ''">
                      {{ check.since ? formatDuration(check.since) : '—' }}
                    </td>
                    <td class="py-1.5 pr-3 text-muted-foreground whitespace-nowrap tabular-nums">
                      {{ check.last_checked ? formatChecked(check.last_checked) : '—' }}
                    </td>
                    <td class="py-1.5 text-right whitespace-nowrap">
                      <button
                        v-if="icinga2Sources.has(check.source)"
                        class="mr-2 text-xs transition-colors"
                        :class="{
                          'text-muted-foreground hover:text-foreground': recheckState.get(check.id) === 'idle' || !recheckState.has(check.id),
                          'text-muted-foreground/50 cursor-wait': recheckState.get(check.id) === 'loading',
                          'text-green-600': recheckState.get(check.id) === 'done',
                          'text-red-500': recheckState.get(check.id) === 'error',
                        }"
                        :disabled="recheckState.get(check.id) === 'loading'"
                        :title="recheckState.get(check.id) === 'done' ? 'Rechecked' : recheckState.get(check.id) === 'error' ? 'Failed' : 'Force recheck'"
                        @click="doRecheck(check.source, check.id)"
                      >
                        {{
                          recheckState.get(check.id) === 'loading' ? '…'
                          : recheckState.get(check.id) === 'done' ? '✓'
                          : recheckState.get(check.id) === 'error' ? '✗'
                          : '↺'
                        }}
                      </button>
                      <button
                        v-if="icinga2Sources.has(check.source) && !check.acknowledged"
                        class="mr-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
                        title="Acknowledge"
                        @click="openActionModal('ack', check.source, check.id, check.name)"
                      >Ack</button>
                      <button
                        v-if="(icinga2Sources.has(check.source) || prometheusSources.has(check.source)) && !check.in_downtime"
                        class="mr-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
                        :title="prometheusSources.has(check.source) ? 'Silence' : 'Schedule downtime'"
                        @click="openActionModal('downtime', check.source, check.id, check.name)"
                      >{{ prometheusSources.has(check.source) ? 'SIL' : 'DT' }}</button>
                      <button
                        class="text-muted-foreground hover:text-foreground transition-colors"
                        :title="openNotes.has(check.id) ? 'Hide notes' : 'Notes'"
                        @click="toggleNotes(check.id, check.source, check.name, check.host)"
                      >
                        {{ openNotes.has(check.id) ? '▲' : '✎' }}
                      </button>
                    </td>
                  </tr>

                  <!-- Notes expansion row -->
                  <tr
                    v-if="openNotes.has(check.id)"
                    :key="`${check.id}-notes`"
                  >
                    <td colspan="7" class="px-3 pb-3 pt-2 bg-muted/20 border-b border-border/40">
                      <pre v-if="check.output" class="text-xs text-muted-foreground font-mono whitespace-pre-wrap break-words mb-3 pb-3 border-b border-border/40">{{ check.output }}</pre>
                      <p v-if="loadingNotes.has(check.id)" class="text-muted-foreground">Loading…</p>
                      <template v-else>
                        <p
                          v-if="(notesCache[check.id] ?? []).length === 0"
                          class="text-muted-foreground"
                        >No notes yet.</p>
                        <div
                          v-for="note in notesCache[check.id] ?? []"
                          :key="note.id"
                          class="flex items-start gap-2 py-0.5"
                        >
                          <div class="flex-1 min-w-0">
                            <span :class="note.resolved ? 'line-through text-muted-foreground/50' : 'text-foreground'">{{ note.content }}</span>
                            <span class="ml-2 text-muted-foreground/50">
                              {{ note.host ? note.host : 'general' }} · {{ new Date(note.created_at).toLocaleString('sk-SK') }} · {{ note.author }}
                            </span>
                          </div>
                          <div class="shrink-0 flex gap-1">
                            <button
                              class="text-muted-foreground hover:text-foreground transition-colors"
                              :title="note.resolved ? 'Reopen' : 'Mark resolved'"
                              @click="toggleResolved(note, check.id, check.source, check.name, check.host)"
                            >{{ note.resolved ? '↩' : '✓' }}</button>
                            <button
                              class="text-muted-foreground hover:text-red-500 transition-colors"
                              title="Delete"
                              @click="removeNote(note.id, check.id, check.source, check.name, check.host)"
                            >×</button>
                          </div>
                        </div>
                        <label class="flex items-center gap-1.5 text-xs text-muted-foreground mt-2 cursor-pointer select-none">
                          <input
                            v-model="noteGeneral[check.id]"
                            type="checkbox"
                            class="accent-foreground"
                          />
                          General ({{ check.source }} · {{ check.name }})
                        </label>
                        <div class="flex gap-2 mt-1">
                          <input
                            v-model="newNoteContent[check.id]"
                            type="text"
                            placeholder="Add a note…"
                            class="flex-1 bg-background border border-border rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-ring"
                            @keydown.enter="submitNote(check.id, check.source, check.name, check.host)"
                          />
                          <button
                            class="px-2 py-1 rounded bg-muted hover:bg-muted/80 text-foreground transition-colors"
                            @click="submitNote(check.id, check.source, check.name, check.host)"
                          >Add</button>
                        </div>
                      </template>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </template>
        </div>
      </div>
    </main>

    <!-- Ack / Downtime modal -->
    <Teleport to="body">
      <div
        v-if="actionModal"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        @click.self="closeActionModal"
      >
        <div class="bg-background border border-border rounded-lg shadow-xl w-full max-w-md mx-4 p-6">
          <h2 class="text-base font-semibold text-foreground mb-1">
            {{ actionModal.type === 'ack' ? 'Acknowledge' : 'Schedule downtime' }}
          </h2>
          <p class="text-xs text-muted-foreground mb-4">{{ actionModal.checkName }}</p>

          <label class="text-xs text-muted-foreground block mb-1">Comment *</label>
          <textarea
            v-model="actionComment"
            class="w-full text-sm bg-background border border-border rounded px-3 py-2 focus:outline-none focus:ring-1 focus:ring-ring resize-none"
            rows="3"
            placeholder="Describe the situation…"
            :disabled="actionSubmitting"
          ></textarea>

          <div class="mt-4 mb-2 flex items-center justify-between">
            <label class="text-xs text-muted-foreground">Expiry</label>
            <div class="flex gap-1">
              <button
                class="text-xs px-2 py-0.5 rounded transition-colors"
                :class="actionExpiryMode === 'slider' ? 'bg-foreground text-background' : 'border border-border text-muted-foreground hover:text-foreground'"
                @click="actionExpiryMode = 'slider'"
              >Quick</button>
              <button
                class="text-xs px-2 py-0.5 rounded transition-colors"
                :class="actionExpiryMode === 'datetime' ? 'bg-foreground text-background' : 'border border-border text-muted-foreground hover:text-foreground'"
                @click="actionExpiryMode = 'datetime'"
              >Exact</button>
            </div>
          </div>

          <div v-if="actionExpiryMode === 'slider'" class="space-y-1">
            <input
              v-model.number="actionExpiryHours"
              type="range" min="1" max="24" step="1"
              class="w-full accent-foreground"
              :disabled="actionSubmitting"
            />
            <p class="text-xs text-center text-muted-foreground">
              {{ actionExpiryHours }} hour{{ actionExpiryHours !== 1 ? 's' : '' }} from now
            </p>
          </div>

          <div v-else>
            <input
              v-model="actionExpiryDatetime"
              type="datetime-local"
              class="w-full text-sm bg-background border border-border rounded px-3 py-2 focus:outline-none focus:ring-1 focus:ring-ring"
              :disabled="actionSubmitting"
            />
          </div>

          <div class="flex justify-end gap-3 mt-6">
            <button
              class="text-sm text-muted-foreground hover:text-foreground transition-colors"
              :disabled="actionSubmitting"
              @click="closeActionModal"
            >Cancel</button>
            <button
              class="text-sm px-4 py-1.5 bg-foreground text-background rounded disabled:opacity-40 transition-opacity"
              :disabled="!actionComment.trim() || actionSubmitting"
              @click="submitActionModal"
            >
              {{ actionSubmitting ? 'Saving…' : actionModal.type === 'ack' ? 'Acknowledge' : 'Schedule downtime' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Output modal -->
    <Teleport to="body">
      <div
        v-if="outputModal"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        @click.self="closeOutputModal"
      >
        <div class="bg-background border border-border rounded-lg shadow-xl w-full max-w-2xl mx-4 flex flex-col max-h-[80vh]">
          <div class="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
            <span class="text-sm font-medium text-foreground">{{ outputModal.name }}</span>
            <button
              class="text-muted-foreground hover:text-foreground transition-colors text-lg leading-none"
              title="Close (Esc)"
              @click="closeOutputModal"
            >×</button>
          </div>
          <pre class="p-4 text-xs text-foreground font-mono overflow-auto whitespace-pre-wrap break-words">{{ outputModal.output }}</pre>
        </div>
      </div>
    </Teleport>

    <!-- SSH settings modal -->
    <Teleport to="body">
      <div
        v-if="sshSettingsOpen"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        @click.self="closeSshSettings"
      >
        <div class="bg-background border border-border rounded-lg shadow-xl w-full max-w-sm mx-4 p-5">
          <h2 class="text-sm font-semibold text-foreground mb-4">SSH command prefix</h2>
          <div class="flex items-center gap-2 mb-1">
            <input
              v-model="sshPrefixInput"
              class="flex-1 bg-transparent border border-border rounded px-3 py-1.5 text-sm text-foreground outline-none focus:border-foreground/60"
              placeholder="ssh"
              spellcheck="false"
              @keydown.enter="saveSshSettings"
              @keydown.esc="closeSshSettings"
            />
            <span class="text-sm text-muted-foreground font-mono">hostname</span>
          </div>
          <p class="text-xs text-muted-foreground mb-4">
            Preview: <span class="font-mono">{{ (sshPrefixInput.trim() || 'ssh') }} hostname</span>
          </p>
          <div class="flex justify-end gap-3">
            <button
              class="text-sm text-muted-foreground hover:text-foreground transition-colors"
              :disabled="sshSettingsSaving"
              @click="closeSshSettings"
            >Cancel</button>
            <button
              class="text-sm px-4 py-1.5 bg-foreground text-background rounded disabled:opacity-40 transition-opacity"
              :disabled="!sshPrefixInput.trim() || sshSettingsSaving"
              @click="saveSshSettings"
            >
              {{ sshSettingsSaving ? 'Saving…' : 'Save' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
