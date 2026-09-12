import { useCallback, useEffect, useState } from 'react'
import * as api from '../api'
import type { Scan } from '../types'
import { fmtTime } from '../format'
import { Badge, Empty, ErrorBanner } from '../ui'

interface Props {
  onOpen: (id: number) => void
}

export default function Scans({ onOpen }: Props) {
  const [scans, setScans] = useState<Scan[]>([])
  const [total, setTotal] = useState(0)
  const [error, setError] = useState('')
  const [form, setForm] = useState({ targetType: 'email', targetValue: '', scanMode: 'local' })
  const [busy, setBusy] = useState('')

  const load = useCallback(() => {
    api.getScans().then((p) => { setScans(p.data); setTotal(p.pagination.totalItems) }).catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => { load() }, [load])

  const create = async () => {
    if (!form.targetValue.trim()) { setError('Target value required'); return }
    setBusy('Creating scan…')
    try {
      const scan = await api.createScan(form.targetType, form.targetValue.trim(), form.scanMode)
      setBusy('')
      onOpen(scan.id)
    } catch (e) {
      setError((e as Error).message)
      setBusy('')
    }
  }

  const run = async (id: number) => {
    setBusy('Starting investigation…')
    try {
      await api.runScan(id)
      setBusy('')
      load()
    } catch (e) {
      setError((e as Error).message)
      setBusy('')
    }
  }

  return (
    <div className="page">
      <h2>Scans</h2>
      <ErrorBanner message={error} />
      <div className="panel">
        <h3>New scan</h3>
        <div className="form-row">
          <select value={form.targetType} onChange={(e) => setForm({ ...form, targetType: e.target.value })}>
            <option value="email">Email</option>
            <option value="username">Username</option>
            <option value="image">Image</option>
            <option value="custom">Custom</option>
          </select>
          <input value={form.targetValue} onChange={(e) => setForm({ ...form, targetValue: e.target.value })}
            placeholder={form.targetType === 'image' ? 'upload happens on detail page' : 'target value'} />
          <button className="btn" onClick={() => void create()} disabled={busy !== ''}>{busy || 'Create'}</button>
        </div>
      </div>
      <h3>{total} scan(s)</h3>
      {scans.length ? (
        <table className="data-table">
          <thead><tr><th>ID</th><th>Target</th><th>Type</th><th>Mode</th><th>Status</th><th>Created</th><th>Actions</th></tr></thead>
          <tbody>
            {scans.map((s) => (
              <tr key={s.id} className="row-click" onClick={() => onOpen(s.id)}>
                <td>{s.id}</td>
                <td className="cell-mono">{s.targetValue}</td>
                <td><Badge status="reviewed" label={s.targetType} /></td>
                <td>{s.scanMode}</td>
                <td><Badge status={s.status} /></td>
                <td>{fmtTime(s.createdAt)}</td>
                <td>
                  <button className="btn btn-sm" onClick={(e) => { e.stopPropagation(); onOpen(s.id) }}>open</button>{' '}
                  {s.status !== 'running' && <button className="btn btn-sm" onClick={(e) => { e.stopPropagation(); void run(s.id) }}>run</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <Empty>No scans yet — create one above.</Empty>
      )}
    </div>
  )
}