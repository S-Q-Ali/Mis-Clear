import { useEffect, useState } from 'react'
import * as api from '../api'
import type { Settings as SettingsShape } from '../types'
import { Badge, ErrorBanner, Spinner } from '../ui'

function fmtBytes(n: number): string {
  if (n >= 1024 * 1024) return `${Math.round(n / (1024 * 1024))} MB`
  if (n >= 1024) return `${Math.round(n / 1024)} KB`
  return `${n} B`
}

export default function Settings() {
  const [settings, setSettings] = useState<SettingsShape | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getSettings().then(setSettings).catch((e: Error) => setError(e.message))
  }, [])

  if (!settings && !error) return <div className="page"><Spinner /></div>
  const s = settings

  return (
    <div className="page">
      <h2>Settings</h2>
      <ErrorBanner message={error} />
      {s ? (
        <>
          <div className="privacy-note">
            Read-only view. Every value here is governance-driven: OSINT toggles,
            hybrid/Colab approval gates, and upload limits. No value can be changed
            from this screen by design — configuration lives on the operator's
            laptop only.
          </div>
          <table className="data-table kv">
            <tbody>
              <tr><th>OSINT adapters</th><td><Badge status={s.osintEnabled ? 'completed' : 'weak'} label={s.osintEnabled ? 'enabled' : 'disabled'} /></td></tr>
              <tr><th>Default scan mode</th><td>{s.defaultScanMode}</td></tr>
              <tr><th>Hybrid requires explicit approval</th><td>{s.hybridRequiresExplicitApproval ? 'yes' : 'no'}</td></tr>
              <tr><th>Local AI</th><td><Badge status={s.localAiAvailable ? 'completed' : s.localAiConfigured ? 'running' : 'failed'} label={s.localAiAvailable ? 'available' : s.localAiConfigured ? 'configured, offline' : 'not configured'} /></td></tr>
              <tr><th>Colab AI (tunnel)</th><td><Badge status={s.colabAiAvailable ? 'completed' : s.colabAiConfigured ? 'running' : 'failed'} label={s.colabAiAvailable ? 'available' : s.colabAiConfigured ? 'configured, offline' : 'not configured'} /></td></tr>
              <tr><th>Colab job dispatcher</th><td><Badge status={s.colabDispatcherConfigured ? 'completed' : 'failed'} label={s.colabDispatcherConfigured ? 'configured' : 'not configured'} /></td></tr>
              <tr><th>Colab approval required</th><td>{String(s.colabApprovalRequired)}</td></tr>
              <tr><th>Max upload size</th><td>{fmtBytes(s.uploadMaxBytes)}</td></tr>
            </tbody>
          </table>
        </>
      ) : null}
    </div>
  )
}