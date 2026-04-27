import { client } from './client'
import type { Note } from '@/types'

export interface NoteCreate {
  source: string
  check_name: string
  host?: string | null
  content: string
}

export interface NoteUpdate {
  content?: string
  resolved?: boolean
}

export async function listNotes(source: string, checkName: string, host?: string | null): Promise<Note[]> {
  const params = new URLSearchParams({ source, check_name: checkName })
  if (host) params.set('host', host)
  return client.request<Note[]>(`/notes?${params}`)
}

export async function createNote(body: NoteCreate): Promise<Note> {
  return client.request<Note>('/notes', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function updateNote(id: string, body: NoteUpdate): Promise<Note> {
  return client.request<Note>(`/notes/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export async function deleteNote(id: string): Promise<void> {
  await fetch(`/api/notes/${id}`, {
    method: 'DELETE',
    credentials: 'include',
  })
}
