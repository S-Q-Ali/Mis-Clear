import { useState } from 'react'
import Actions from './views/Actions'
import Dashboard from './views/Dashboard'
import Logs from './views/Logs'
import Scans from './views/Scans'
import Settings from './views/Settings'
import ScanDetail, { type DetailTab } from './views/ScanDetail'
import Workers from './views/Workers'
import './App.css'

type View = 'dashboard' | 'scans' | 'overview' | 'findings' | 'graph' | 'photo' | 'actions' | 'logs' | 'workers' | 'settings'

const NAV: { key: View; label: string; needsScan?: boolean }[] = [
  { key: 'dashboard', label: 'Dashboard' },
  { key: 'scans', label: 'Scans' },
  { key: 'overview', label: 'Live investigation', needsScan: true },
  { key: 'findings', label: 'Findings & evidence', needsScan: true },
  { key: 'graph', label: 'Identity graph', needsScan: true },
  { key: 'photo', label: 'Photo analysis', needsScan: true },
  { key: 'actions', label: 'Privacy actions' },
  { key: 'workers', label: 'Worker status' },
  { key: 'settings', label: 'Settings' },
  { key: 'logs', label: 'Logs' },
]

function App() {
  const [view, setView] = useState<View>('dashboard')
  const [scanId, setScanId] = useState<number | null>(null)

  const openScan = (id: number) => {
    setScanId(id)
    setView('overview')
  }

  const openFromSidebar = (v: View) => {
    if (v === 'overview' || v === 'findings' || v === 'graph' || v === 'photo') {
      if (scanId === null) {
        setView('scans')
        return
      }
    }
    setView(v)
  }

  const scanNeededCard = (
    <div className="page">
      <h2>Select a scan first</h2>
      <p className="muted">This view shows details for one investigation. Pick a scan from the Scans page.</p>
      <button className="btn" onClick={() => setView('scans')}>Go to Scans</button>
    </div>
  )

  const tabFor = (v: View): DetailTab =>
    v === 'findings' ? 'findings' : v === 'graph' ? 'graph' : v === 'photo' ? 'photo' : 'overview'

  const onDetailTab = (t: DetailTab) =>
    setView(t === 'findings' ? 'findings' : t === 'graph' ? 'graph' : t === 'photo' ? 'photo' : 'overview')

  const scanDetailView = (v: View) => {
    if (scanId === null) return scanNeededCard
    return (
      <ScanDetail
        scanId={scanId}
        tab={tabFor(v)}
        onBack={() => setView('scans')}
        onTabChange={onDetailTab}
      />
    )
  }

  const isScanScoped = view === 'overview' || view === 'findings' || view === 'graph' || view === 'photo'

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">PG</span>
          <div>
            <div className="brand-name">Privacy Guardian</div>
            <div className="brand-sub">local-first OSINT assistant</div>
          </div>
        </div>
        <nav>
          {NAV.map((item) => (
            <button
              key={item.key}
              className={`nav-item ${view === item.key ? 'nav-active' : ''}`}
              onClick={() => openFromSidebar(item.key)}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">laptop is the system of record</div>
      </aside>
      <main className="content">
        {view === 'dashboard' && <Dashboard onViewScan={openScan} />}
        {view === 'scans' && <Scans onOpen={openScan} />}
        {isScanScoped && scanDetailView(view)}
        {view === 'actions' && <Actions />}
        {view === 'workers' && <Workers />}
        {view === 'settings' && <Settings />}
        {view === 'logs' && <Logs />}
      </main>
    </div>
  )
}

export default App