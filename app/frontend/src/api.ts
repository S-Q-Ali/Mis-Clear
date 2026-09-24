import type {
  AgentConversation,
  AgentConversationDetail,
  AgentDone,
  AgentStatus,
  AgentStreamEvent,
  Graph,
  Finding,
  ImageDetails,
  LogEntry,
  Paginated,
  PrivacyAction,
  RemovalResult,
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
export const removeAction = (id: number) =>
  api<PrivacyAction>(`/api/actions/${id}/remove`, { method: 'POST' })
export const removeFinding = (findingId: number) =>
  api<RemovalResult>(`/api/findings/${findingId}/remove`, { method: 'POST' })
export const getAction = (id: number) => api<PrivacyAction>(`/api/actions/${id}`)

export const getLogs = (page = 1, pageSize = 30) =>
  api<Paginated<LogEntry>>(`/api/logs?page=${page}&pageSize=${pageSize}`)
export const getWorkerStatus = () => api<WorkerStatus>('/api/workers')
export const getSettings = () => api<Settings>('/api/settings')
export const getHealth = () => api<{ status: string }>('/api/health')

export const getAgentStatus = () => api<AgentStatus>('/api/agent/status')
export const getAgentConversations = () => api<AgentConversation[]>('/api/agent/conversations')
export const getAgentConversation = (id: number) =>
  api<AgentConversationDetail>(`/api/agent/conversations/${id}`)

function parseSseFrame(frame: string): AgentStreamEvent | null {
  let kind = ''
  let data = ''
  for (const line of frame.split('\n')) {
    if (line.startsWith('event: ')) kind = line.slice('event: '.length)
    else if (line.startsWith('data: ')) data = line.slice('data: '.length)
  }
  if (!kind || !data) return null
  try {
    const parsed = JSON.parse(data) as AgentStreamEvent
    parsed.kind = kind as AgentStreamEvent['kind']
    return parsed
  } catch {
    return null
  }
}

export async function streamAgentChat(
  message: string,
  approveHybrid: boolean,
  onEvent: (evt: AgentStreamEvent) => void,
): Promise<AgentDone> {
  const res = await fetch(`${BASE}/api/agent/chat`, {
    method: 'POST',
    headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, approveHybrid }),
  })
  if (res.status === 429) throw new Error('Too many agent requests (rate limited)')
  if (!res.ok) {
    let msg = `Agent request failed (${res.status})`
    try {
      const body = await res.json()
      if (body?.error?.message) msg = body.error.message
    } catch {
      /* keep default */
    }
    throw new Error(msg)
  }
  if (!res.body) throw new Error('Streaming not supported by this browser')
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let done: AgentDone | null = null
  for (;;) {
    const { value, done: streamDone } = await reader.read()
    if (streamDone) break
    buffer += decoder.decode(value, { stream: true })
    let idx = -1
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      const evt = parseSseFrame(frame)
      if (evt) {
        onEvent(evt)
        if (evt.kind === 'done') done = evt as unknown as AgentDone
      }
    }
  }
  if (!done) throw new Error('Agent stream ended without a result')
  return done
}

export { api }
export type { ApiOptions }