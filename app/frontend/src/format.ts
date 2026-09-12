export function fmtTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

export function statusClass(status: string): string {
  const map: Record<string, string> = {
    pending: 'st-pending',
    running: 'st-running',
    completed: 'st-completed',
    failed: 'st-failed',
    interrupted: 'st-failed',
    approved: 'st-completed',
    declined: 'st-failed',
    expired: 'st-failed',
    open: 'st-pending',
    reviewed: 'st-running',
    resolved: 'st-completed',
    queued: 'st-pending',
    informational: 'sev-info',
    low: 'sev-low',
    medium: 'sev-medium',
    high: 'sev-high',
    critical: 'sev-critical',
    negligible: 'sev-low',
    possible: 'st-pending',
    probable: 'st-running',
    confirmed: 'st-completed',
    weak: 'st-pending',
    false_positive: 'st-failed',
  }
  return map[status] ?? 'st-pending'
}