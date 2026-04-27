export interface User {
  id: string
  email: string
  is_active: boolean
  is_superuser: boolean
  is_verified: boolean
}

export type CheckStatus = 'warning' | 'critical' | 'unknown'

export interface Check {
  id: string
  name: string
  host: string
  source: string
  status: CheckStatus
  output: string
  since: string | null
  last_checked: string | null
  acknowledged: boolean
  in_downtime: boolean
  ack_comment: string | null
  ack_expiry: string | null
  downtime_comment: string | null
  downtime_expiry: string | null
  url: string | null
}

export interface Section {
  name: string
  description: string
  checks: Check[]
}

export interface SourceStatus {
  name: string
  type: string
  available: boolean
  last_updated: string | null
}

export interface DashboardData {
  sections: Section[]
  sources: SourceStatus[]
}

export interface Note {
  id: string
  content: string
  check_name: string
  source: string | null
  host: string | null
  author: string
  resolved: boolean
  created_at: string
  updated_at: string
}
