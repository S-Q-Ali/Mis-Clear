import { useCallback, useEffect, useState } from 'react'
import * as api from '../api'
import type { Finding, Graph, ImageDetails, Scan, ScanRisk, ToolRun } from '../types'
import { fmtTime } from '../format'
import { Badge, Empty, ErrorBanner, Spinner } from '../ui'

export type DetailTab = 'overview' | 'findings' | 'graph' | 'photo'

interface Props {
  scanId: number
  tab: DetailTab
  onBack: () => void
  onTabChange: (tab: DetailTab) => void
}

function useScanDetail(scanId: number) {
  const [scan, setScan] = useState<Scan | null>(null)
  const [findings, setFindings] = useState<Finding[]>([])
  const [runs, setRuns] = useState<ToolRun[]>([])
  const [risk, setRisk] = useState<ScanRisk | null>(null)
  const [image, setImage] = useState<ImageDetails | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [sc, fds, trs, rk] = await Promise.all([
        api.getScan(scanId),
        api.getFindings(scanId, 1, 200).then((p) => p.data),
        api.getToolRuns(scanId).then((p) => p.data),
        api.getRisk(scanId).catch(() => null),
      ])
      setScan(sc)
      setFindings(fds)
      setRuns(trs)
      setRisk(rk)
      setError('')
      if (sc.targetType === 'image') {
        api.getImage(scanId).then(setImage).catch(() => setImage(null))
      }
    } catch (e) {
      setError((e as Error).message)
    }
  }, [scanId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    if (!scan || scan.status !== 'running') return
    const timer = window.setInterval(() => void refresh(), 1500)
    return () => window.clearInterval(timer)
  }, [scan, refresh])

  return { scan, findings, runs, risk, image, error, busy, refresh, setBusy, setError }
}

export default function ScanDetail({ scanId, tab, onBack, onTabChange }: Props) {
  const s = useScanDetail(scanId)
  const { scan, findings, runs, risk, image, error, busy } = s

  if (error && !scan) return <div className="page"><ErrorBanner message={error} /><button className="btn" onClick={onBack}>← Back</button></div>
  if (!scan) return <div className="page"><Spinner /></div>

  const run = async (tools?: string[]) => {
    s.setBusy('Running scan…')
    try {
      await api.runScan(scanId, tools)
      await s.refresh()
      s.setBusy('')
    } catch (e) {
      s.setError((e as Error).message)
      s.setBusy('')
    }
  }
  const doResearch = async () => {
    s.setBusy('Researching deletion options…')
    try {
      const r = await api.researchScan(scanId)
      s.setBusy(`Deletion research done: ${r.created} created, ${r.skipped} skipped`)
    } catch (e) {
      s.setError((e as Error).message)
      s.setBusy('')
    }
  }

  return (
    <div className="page">
      <ErrorBanner message={error} />
      <div className="scan-head">
        <button className="btn btn-sm" onClick={onBack}>← Scans</button>
        <h2 className="inline-h2">{scan.targetValue}</h2>
        <Badge status={scan.status} />
        <span className="muted">ID {scan.id} · {scan.targetType} · {scan.scanMode}</span>
      </div>
      {scan.error && <ErrorBanner message={`Scan error: ${scan.error}`} />}

      <div className="tabs">
        <button className={`tab ${tab === 'overview' ? 'tab-active' : ''}`} onClick={() => onTabChange('overview')}>Live investigation</button>
        <button className={`tab ${tab === 'findings' ? 'tab-active' : ''}`} onClick={() => onTabChange('findings')}>Findings &amp; evidence</button>
        <button className={`tab ${tab === 'graph' ? 'tab-active' : ''}`} onClick={() => onTabChange('graph')}>Identity graph</button>
        <button className={`tab ${tab === 'photo' ? 'tab-active' : ''}`} onClick={() => onTabChange('photo')}>Photo analysis</button>
      </div>

      {busy && <div className="busy">{busy}</div>}

      {tab === 'overview' && (
        <Overview scan={scan} runs={runs} risk={risk} running={scan.status === 'running'} onRun={() => run()} onResearch={doResearch} />
      )}
      {tab === 'findings' && <Findings findings={findings} />}
      {tab === 'graph' && <GraphView scanId={scan.id} />}
      {tab === 'photo' && <PhotoView scan={scan} image={image} onUploaded={() => void s.refresh()} onError={(m) => s.setError(m)} />}
    </div>
  )
}

function formatCoverage(coverage: Record<string, unknown> | null): string {
  if (!coverage) return '—'
  const c = coverage as Record<string, number>
  if (c.sources_checked === undefined || c.sources_total === undefined) return JSON.stringify(coverage)
  return `${c.sources_checked}/${c.sources_total}`
}

function Overview({ scan, runs, risk, running, onRun, onResearch }: {
  scan: Scan
  runs: ToolRun[]
  risk: ScanRisk | null
  running: boolean
  onRun: () => void
  onResearch: () => void
}) {
  return (
    <div className="overview">
      {running && <div className="live-note"><Spinner /> Live investigation in progress — updating automatically.</div>}
      <div className="actions-row">
        {scan.status !== 'running' && <button className="btn" onClick={onRun}>Run investigation</button>}
        <button className="btn" onClick={onResearch}>Deletion research</button>
      </div>
      <div className="cards">
        <div className="card"><span className="card-label">Risk score</span>
          <span className="card-value">{risk ? risk.riskScore : '—'}</span>
          {risk && <Badge status={risk.level === 'negligible' ? 'completed' : risk.level} label={risk.level} />}
        </div>
        <div className="card"><span className="card-label">Findings</span><span className="card-value">{risk?.findingCount ?? 0}</span></div>
        <div className="card"><span className="card-label">Tools run</span><span className="card-value">{runs.length}</span></div>
        <div className="card"><span className="card-label">Coverage</span>
          <span className="card-value">{formatCoverage(scan.coverage)}</span>
        </div>
      </div>
      <h3>Tool runs</h3>
      {runs.length ? (
        <table className="data-table">
          <thead><tr><th>Tool</th><th>Status</th><th>Findings</th><th>Duration (ms)</th><th>Detail</th></tr></thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id}>
                <td className="cell-mono">{r.tool}</td>
                <td><Badge status={r.status} /></td>
                <td>{r.findingsCount}</td>
                <td>{r.durationMs}</td>
                <td className="muted">{r.coverage || r.errors?.join(', ') || ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <Empty>No tool runs yet.</Empty>}
      {risk && risk.findings.length > 0 && (
        <>
          <h3>Risk breakdown</h3>
          <table className="data-table">
            <thead><tr><th>Finding</th><th>Type</th><th>Score</th><th>Level</th><th>Confidence</th><th>Reliability</th></tr></thead>
            <tbody>
              {risk.findings.map((f) => (
                <tr key={f.findingId}>
                  <td>{f.title}</td>
                  <td>{f.type}</td>
                  <td>{f.riskScore}/100</td>
                  <td><Badge status={f.level === 'negligible' ? 'completed' : f.level} label={f.level} /></td>
                  <td>{Math.round(f.breakdown.confidence * 100)}%</td>
                  <td>{Math.round(f.breakdown.sourceReliability * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {scan.coverage && (
        <div className="muted note">Coverage: {JSON.stringify(scan.coverage)}</div>
      )}
    </div>
  )
}

function Findings({ findings }: { findings: Finding[] }) {
  if (!findings.length) return <Empty>No findings yet.</Empty>
  return (
    <div className="findings">
      {findings.map((f) => (
        <details key={f.id} className="finding">
          <summary>
            <span className="finding-title">{f.title}</span>
            <Badge status={f.severity} label={f.severity} />
            <Badge status={f.confidence} label={f.confidence} />
          </summary>
          <div className="finding-body">
            <p><strong>Source:</strong> {f.source} {f.tool ? `(tool: ${f.tool})` : ''}</p>
            {f.url && <p><strong>URL:</strong> <a href={f.url} target="_blank" rel="noreferrer noopener">{f.url}</a></p>}
            <p><strong>Evidence:</strong> <span className="cell-mono">{f.evidence || '—'}</span></p>
            <p className="muted">Found {fmtTime(f.timestamp)} · status {f.status} · {f.type}</p>
          </div>
        </details>
      ))}
    </div>
  )
}

function GraphView({ scanId }: { scanId: number }) {
  const [graph, setGraph] = useState<Graph | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api.getGraph(scanId).then(setGraph).catch((e: Error) => setError(e.message))
  }, [scanId])

  useEffect(() => { load() }, [load])

  if (error) return <ErrorBanner message={error} />
  if (!graph) return <Spinner />
  if (!graph.nodes.length) {
    return (
      <div className="page-inner">
        <Empty>No graph yet — run the investigation first.</Empty>
        <button className="btn" onClick={() => api.rebuildGraph(scanId).then(setGraph).catch((e: Error) => setError(e.message))}>Rebuild graph</button>
      </div>
    )
  }

  const width = 640
  const height = 420
  const cx = width / 2
  const cy = height / 2
  const R = Math.min(cx, cy) - 36
  const pos = new Map<number, { x: number; y: number }>()
  const n = graph.nodes.length
  graph.nodes.forEach((node, i) => {
    const angle = -Math.PI / 2 + (i / n) * Math.PI * 2
    pos.set(node.id, { x: cx + R * Math.cos(angle), y: cy + R * Math.sin(angle) })
  })
  const kindColor: Record<string, string> = {
    email: '#4cc9f0', username: '#f72585', profile: '#b5179e', domain: '#f8961e',
    website: '#43aa8b', image: '#90be6d', source: '#adb5bd', custom: '#8d99ae',
  }

  return (
    <div>
      <div className="actions-row">
        <button className="btn btn-sm" onClick={() => api.rebuildGraph(scanId).then(setGraph).catch((e: Error) => setError(e.message))}>Rebuild graph</button>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="graph-svg" role="img" aria-label="Identity graph">
        {graph.edges.map((e, i) => {
          const a = pos.get(e.source)
          const b = pos.get(e.target)
          if (!a || !b) return null
          return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} className="graph-edge" />
        })}
        {graph.nodes.map((node) => {
          const p = pos.get(node.id)
          if (!p) return null
          return (
            <g key={node.id}>
              <circle cx={p.x} cy={p.y} r={14} fill={kindColor[node.kind] ?? '#8d99ae'} className="graph-node" />
              <text x={p.x} y={p.y + 32} textAnchor="middle" className="graph-label">{node.value.length > 16 ? node.value.slice(0, 15) + '…' : node.value}</text>
            </g>
          )
        })}
      </svg>
      <h4>Edges</h4>
      {graph.edges.length ? (
        <ul className="edge-list">
          {graph.edges.map((e, i) => {
            const s = graph.nodes.find((nn) => nn.id === e.source)
            const t = graph.nodes.find((nn) => nn.id === e.target)
            return <li key={i} className="muted">{s?.value ?? e.source} → <strong>{e.type}</strong> → {t?.value ?? e.target}</li>
          })}
        </ul>
      ) : <Empty>No relationships yet.</Empty>}
    </div>
  )
}

function PhotoView({ scan, image, onUploaded, onError }: {
  scan: Scan
  image: ImageDetails | null
  onUploaded: () => void
  onError: (m: string) => void
}) {
  const [uploading, setUploading] = useState(false)

  const handleFile = async (file: File | undefined) => {
    if (!file) return
    setUploading(true)
    try {
      await api.uploadImage(scan.id, file, file.name)
      onUploaded()
    } catch (e) {
      onError((e as Error).message)
    } finally {
      setUploading(false)
    }
  }

  if (scan.targetType !== 'image') {
    return (
      <div className="page-inner">
        <Empty>This scan is not an image target. Create a scan with target type <strong>image</strong>, then upload a photo here.</Empty>
      </div>
    )
  }

  return (
    <div className="page-inner">
      <label className="file-btn">
        {uploading ? 'Analyzing…' : 'Upload photo for analysis'}
        <input type="file" accept="image/*" hidden onChange={(e) => void handleFile(e.target.files?.[0])} disabled={uploading} />
      </label>
      {image ? (
        <div>
          <h4>Stored image</h4>
          <p className="muted">File: {image.filename} · local: <span className="cell-mono">{image.localPath}</span></p>
          <table className="data-table">
            <tbody>
              <tr><th>MD5</th><td className="cell-mono">{image.md5 ?? '—'}</td></tr>
              <tr><th>SHA-256</th><td className="cell-mono">{image.sha256 ?? '—'}</td></tr>
              <tr><th>pHash</th><td className="cell-mono">{image.phash ?? '—'}</td></tr>
              <tr><th>EXIF</th><td className="cell-mono">{image.exif ? JSON.stringify(image.exif) : '—'}</td></tr>
            </tbody>
          </table>
        </div>
      ) : (
        <Empty>No image stored for this scan yet.</Empty>
      )}
    </div>
  )
}