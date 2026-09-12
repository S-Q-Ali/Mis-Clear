import { useCallback, useEffect, useState } from 'react'
import * as api from '../api'
import type { LogEntry } from '../types'
import { fmtTime } from '../format'
import { Badge, Empty, ErrorBanner, Spinner } from '../ui'

export default function Logs() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api.getLogs(1, 50).then((p) => setLogs(p.data)).catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => { load() }, [load])

  return (
    <div className="page">
      <h2>Logs</h2>
      <ErrorBanner message={error} />
      <button className="btn" onClick={() => load()}>Refresh</button>
      {!logs.length && !error && <Spinner />}
      {logs.length ? (
        <table className="data-table">
          <thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Entity</th><th>Detail</th></tr></thead>
          <tbody>
            {logs.map((l) => (
              <tr key={l.id}>
                <td>{fmtTime(l.timestamp)}</td>
                <td>{l.actor}</td>
                <td><Badge status={l.action === 'approve' ? 'completed' : l.action === 'run' ? 'running' : l.action === 'delete' ? 'failed' : 'reviewed'} label={l.action} /></td>
                <td className="muted">{l.entityType}{l.entityId !== null ? ` #${l.entityId}` : ''}</td>
                <td>{l.detail ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        !error && <Empty>No log entries yet.</Empty>
      )}
    </div>
  )
}