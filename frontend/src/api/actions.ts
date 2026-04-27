import { client } from './client'

export async function triggerRecheck(source: string, checkId: string): Promise<void> {
  await client.request<void>('/actions/recheck', {
    method: 'POST',
    body: JSON.stringify({ source, check_id: checkId }),
  })
}

export async function removeAck(source: string, checkId: string): Promise<void> {
  await client.request<void>('/actions/remove-ack', {
    method: 'POST',
    body: JSON.stringify({ source, check_id: checkId }),
  })
}

export async function removeDowntime(source: string, checkId: string): Promise<void> {
  await client.request<void>('/actions/remove-downtime', {
    method: 'POST',
    body: JSON.stringify({ source, check_id: checkId }),
  })
}

export async function acknowledge(
  source: string,
  checkId: string,
  comment: string,
  expiryAt: string | null,
): Promise<void> {
  await client.request<void>('/actions/acknowledge', {
    method: 'POST',
    body: JSON.stringify({ source, check_id: checkId, comment, expiry_at: expiryAt }),
  })
}

export async function scheduleDowntime(
  source: string,
  checkId: string,
  comment: string,
  expiryAt: string,
): Promise<void> {
  await client.request<void>('/actions/schedule-downtime', {
    method: 'POST',
    body: JSON.stringify({ source, check_id: checkId, comment, expiry_at: expiryAt }),
  })
}
