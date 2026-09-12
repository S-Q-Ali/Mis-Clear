import type {
  Graph,
  Finding,
  ImageDetails,
  LogEntry,
  Paginated,
  PrivacyAction,
  Report,
  Scan,
  ScanRisk,
  Settings,
  ToolRun,
  WorkerStatus,
} from './types'

const BASE = ''

interface ApiOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  json?: unknown
  form?: FormData
}

async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const init: RequestInit = { method: options.method ?? 'GET' }
  if (options.json !== undefined) {
    init.headers = { Accept: 'application/json', 'Content-Type': 'application/json' }
    init.body = JSON.stringify(options.json)
  } else if (options.form) {
    init.headers = { Accept: 'application/json' }
    init.body = options.form
  } else {
    init.headers = { Accept: 'application/json' }
  }

  const res = await fetch(`${BASE}${path}`, init)
  if (res.status === 404) throw new Error('Not found (404)')
  if (!res.ok) {
    let message = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (body?.error?.message) message = body.error.message
    } catch {
      /* keep the default message */
    }
    throw new Error(message)
  }
  return res.json() as Promise<T>
}

export const getScans = (page = 1, pageSize = 20) =>
  api<Paginated<Scan>>(`/api/scans?page=${page}&pageSize=${pageSize}`)
export const createScan = (targetType: string, targetValue: string, scanMode = 'local') =>
  api<Scan>('/api/scans', {
    method: 'POST',
    json: { targetType, targetValue, scanMode },
  })
export const runScan = (id: number, tools?: string[]) =>
  api<Scan>(`/api/scans/${id}/run`, { method: 'POST', json: { tools: tools ?? [] } })
export const getScan = (id: number) => api<Scan>(`/api/scans/${id}`)
export const getFindings = (id: number, page = 1, pageSize = 50) =>
  api<Paginated<Finding>>(`/api/scans/${id}/findings?page=${page}&pageSize=${pageSize}`)
export const getToolRuns = (id: number) =>
  api<Paginated<ToolRun>>(`/api/scans/${id}/tool-runs?pageSize=100`)
export const getGraph = (id: number) => api<Graph>(`/api/scans/${id}/graph`)
export const rebuildGraph = (id: number) =>
  api<Graph>(`/api/scans/${id}/graph/rebuild`, { method: 'POST' })
export const getRisk = (id: number) => api<ScanRisk>(`/api/scans/${id}/risk`)
export const getReport = (id: number) => api<Report>(`/api/reports/${id}`)
export const researchScan = (id: number) =>
  api<{ scanId: number; researchable: number; created: number; skipped: number }>(
    `/api/scans/${id}/deletion-research`,
    { method: 'POST' },
  )
export const uploadImage = (id: number, file: Blob, filename: string) => {
  const form = new FormData()
  form.append('file', file, filename)
  return api<Scan>(`/api/scans/${id}/image`, { method: 'POST', form })
}
export const getImage = (id: number) => api<ImageDetails>(`/api/scans/${id}/image`)

export const getActions = (scanId?: number, status?: string, page = 1, pageSize = 50) => {
  const params = new URLSearchParams({ page: String(page), pageSize: String(pageSize) })
  if (scanId !== undefined) params.set('scanId', String(scanId))
  if (status) params.set('status', status)
  return api<Paginated<PrivacyAction>>(`/api/actions?${params}`)
}
export const approveAction = (id: number) =>
  api<{ id: number; status: string }>(`/api/actions/${id}/approve`, { method: 'POST' })
export const declineAction = (id: number) =>
  api<{ id: number; status: string }>(`/api/actions/${id}/decline`, { method: 'POST' })

export const getLogs = (page = 1, pageSize = 30) =>
  api<Paginated<LogEntry>>(`/api/logs?page=${page}&pageSize=${pageSize}`)
export const getWorkerStatus = () => api<WorkerStatus>('/api/workers')
export const getSettings = () => api<Settings>('/api/settings')
export const getHealth = () => api<{ status: string }>('/api/health')

export { api }
export type { ApiOptions }