import { useEffect, useState } from 'react'
import * as api from '../api'
import type { WorkerStatus } from '../types'
import { Badge, Spinner } from '../ui'

interface HealthShape {
  status: string
  database?: string
  ai?: string
}

export default function Workers() {
  const [status, setStatus] = useState<WorkerStatus | null>(null)
  const [health, setHealth] = useState<HealthShape | null>(null)

  useEffect(() => {
    api.getWorkerStatus().then(setStatus).catch(() => {})
    api.getHealth().then((h: { status: string }) => setHealth(h)).catch(() => {})
  }, [])

  if (!status) return <div className="page"><Spinner /></div>

  return (
    <div className="page">
      <h2>Worker status</h2>
      <div className="cards">
        <div className="card"><span className="card-label">Mode</span><span className="card-value">{status.mode}</span></div>
        <div className="card"><span className="card-label">API health</span><Badge status={health?.status === 'ok' ? 'completed' : 'failed'} label={health?.status ?? 'unknown'} /></div>
      </div>
      <h3>AI backends</h3>
      <table className="data-table">
        <thead><tr><th>Backend</th><th>Configured</th><th>Available</th></tr></thead>
        <tbody>
          <tr><td>Local Ollama</td><td><Badge status={status.localAiConfigured ? 'completed' : 'weak'} label={status.localAiConfigured ? 'yes' : 'no'} /></td><td><Badge status={status.localAiAvailable ? 'completed' : 'weak'} label={status.localAiAvailable ? 'yes' : 'no'} /></td></tr>
          <tr><td>Colab Ollama (tunnel)</td><td><Badge status={status.colabAiConfigured ? 'completed' : 'weak'} label={status.colabAiConfigured ? 'yes' : 'no'} /></td><td><Badge status={status.colabAiAvailable ? 'completed' : 'weak'} label={status.colabAiAvailable ? 'yes' : 'no'} /></td></tr>
          <tr><td>Colab job dispatcher</td><td><Badge status={status.colabDispatcherConfigured ? 'completed' : 'weak'} label={status.colabDispatcherConfigured ? 'yes' : 'no'} /></td><td>—</td></tr>
        </tbody>
      </table>
      <p className="muted note">Colab is an approved, disposable GPU worker only — the laptop remains the system of record. Hybrid jobs require explicit approval (approvalRequired={String(status.colabApprovalRequired)}).</p>
    </div>
  )
}