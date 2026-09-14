import { useCallback, useEffect, useState } from 'react'
import * as api from '../api'
import type { PrivacyAction } from '../types'
import { fmtTime } from '../format'
import { Badge, Empty, ErrorBanner, Spinner } from '../ui'

export default function Actions() {
  const [actions, setActions] = useState<PrivacyAction[]>([])
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState<number | null>(null)
  const [statusFilter, setStatusFilter] = useState('')

  const load = useCallback(() => {
    api.getActions(undefined, statusFilter || undefined)
      .then((p) => setActions(p.data))
      .catch((e: Error) => setError(e.message))
  }, [statusFilter])

  useEffect(() => { load() }, [load])

  const transition = async (id: number, fn: (i: number) => Promise<{ id: number; status: string }>) => {
    setBusyId(id)
    try {
      await fn(id)
      load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="page">
      <h2>Privacy actions</h2>
      <div className="privacy-note">
        Nothing is ever sent automatically. Each action is a prepared DRAFT request
        that requires your explicit human approval (or decline) before any release.
      </div>
      <ErrorBanner message={error} />
      <div className="form-row">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="declined">Declined</option>
        </select>
        <button className="btn btn-sm" onClick={() => load()}>Refresh</button>
      </div>
      {!actions.length && !error && <Spinner />}
      {actions.length ? (
        <div className="action-list">
          {actions.map((a) => (
            <details key={a.id} className="action">
              <summary>
                <span className="finding-title">{a.recommendedAction}</span>
                <Badge status={a.status} />
                {a.approvalRequired && <span className="muted">· requires approval</span>}
              </summary>
              <div className="finding-body">
                <div className="actions-row">
                  {a.status === 'pending' && (
                    <>
                      <button className="btn btn-sm" disabled={busyId === a.id} onClick={() => void transition(a.id, api.approveAction)}>Approve</button>
                      <button className="btn btn-sm btn-danger" disabled={busyId === a.id} onClick={() => void transition(a.id, api.declineAction)}>Decline</button>
                    </>
                  )}
                  {(a.status === 'pending' || a.status === 'approved') && (
                    <button className="btn btn-sm" disabled={busyId === a.id}
                      onClick={() => void transition(a.id, api.removeAction)}>Remove data</button>
                  )}
                </div>
                {a.siteAdvisory && (
                  <p><strong>Site advisory:</strong> {a.siteAdvisory.category}
                    <span className="muted"> · recommended={a.siteAdvisory.recommended === null ? 'unknown' : String(a.siteAdvisory.recommended)}</span>
                    <span className="muted"> — {a.siteAdvisory.rationale}</span>
                  </p>
                )}
                {a.execution && (
                  <div className="removal-panel">
                    <Badge status={a.execution.status === 'removed' ? 'completed' : (a.execution.status ?? 'pending')} label={a.execution.status ?? '—'} />
                    {a.execution.channel && <span className="muted"> · channel {a.execution.channel}</span>}
                    {a.execution.verificationDetail && <span className="muted"> · verification: {a.execution.verificationDetail}</span>}
                    {a.execution.verifiedAt && <span className="muted"> · verified {fmtTime(a.execution.verifiedAt)}</span>}
                    {a.execution.note && <p className="muted">{a.execution.note}</p>}
                  </div>
                )}
                {a.deletionUrl && <p><strong>Official procedure:</strong> <a href={a.deletionUrl} target="_blank" rel="noreferrer noopener">{a.deletionUrl}</a></p>}
                {a.instructions && <pre className="pre block">{a.instructions}</pre>}
                <p className="muted">Reference {a.evidenceReference ?? '—'} · created {fmtTime(a.createdAt)}{a.approvedAt ? ` · approved ${fmtTime(a.approvedAt)}` : ''}</p>
              </div>
            </details>
          ))}
        </div>
      ) : (
        !error && <Empty>No privacy actions yet. Run deletion research on a scan that produced confirmed findings.</Empty>
      )}
    </div>
  )
}