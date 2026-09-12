import { useEffect, useState } from 'react'
import * as api from '../api'
import type { Scan, WorkerStatus } from '../types'
import { fmtTime } from '../format'
import { Badge, Empty, ErrorBanner, Spinner } from '../ui'

interface Props {
  onViewScan: (id: number) => void
}

export default function Dashboard({ onViewScan }: Props) {
  const [scans, setScans] = useState<Scan[]>([])
  const [total, setTotal] = useState(0)
  const [worker, setWorker] = useState<WorkerStatus | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getScans(1, 8).then((p) => { setScans(p.data); setTotal(p.pagination.totalItems) }).catch((e: Error) => setError(e.message))
    api.getWorkerStatus().then(setWorker).catch(() => {})
  }, [])

  return (
    <div className="page">
      <h2>Dashboard</h2>
      <ErrorBanner message={error} />
      <div className="cards">
        <div className="card">
          <span className="card-label">Scans</span>
          <span className="card-value">{total}</span>
        </div>
        <div className="card">
          <span className="card-label">AI mode</span>
          <span className="card-value">{worker ? worker.mode : '...'}</span>
        </div>
        <div className="card">
          <span className="card-label">Local AI</span>
          <Badge status={worker?.localAiAvailable ? 'completed' : 'weak'} label={worker?.localAiAvailable ? 'available' : worker?.localAiConfigured ? 'offline' : 'not configured'} />
        </div>
        <div className="card">
          <span className="card-label">Colab</span>
          <Badge status={worker?.colabAiAvailable ? 'completed' : 'weak'} label={worker?.colabAiAvailable ? 'available' : worker?.colabAiConfigured ? 'offline' : 'not configured'} />
        </div>
      </div>
      <h3>Recent scans</h3>
      {!scans.length && !error && <Spinner />}
      {!scans.length && !error ? null : (
        scans.length ? (
          <table className="data-table">
            <thead>
              <tr><th>ID</th><th>Target</th><th>Type</th><th>Status</th><th>Created</th><th></th></tr>
            </thead>
            <tbody>
              {scans.map((s) => (
                <tr key={s.id} onClick={() => onViewScan(s.id)} className="row-click">
                  <td>{s.id}</td>
                  <td className="cell-mono">{s.targetValue}</td>
                  <td><Badge status="reviewed" label={s.targetType} /></td>
                  <td><Badge status={s.status} /></td>
                  <td>{fmtTime(s.createdAt)}</td>
                  <td><button className="btn btn-sm" onClick={(e) => { e.stopPropagation(); onViewScan(s.id) }}>open</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty>No scans yet — create one from the Scans page.</Empty>
        )
      )}
    </div>
  )
}