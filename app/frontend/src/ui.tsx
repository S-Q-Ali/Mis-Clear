import type { ReactNode } from 'react'
import { statusClass } from './format'

export function Badge({ status, label }: { status: string; label?: string }) {
  return <span className={`badge ${statusClass(status)}`}>{label ?? status}</span>
}

export function Spinner() {
  return <span className="spinner" aria-label="loading" />
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>
}

export function ErrorBanner({ message }: { message: string }) {
  if (!message) return null
  return <div className="error-banner">{message}</div>
}