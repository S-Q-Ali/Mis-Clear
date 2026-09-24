import { useEffect, useState } from 'react'
import * as api from '../api'
import type {
  AgentConversation,
  AgentConversationDetail,
  AgentDone,
  AgentStatus,
  AgentStreamEvent,
} from '../types'
import { ErrorBanner, Spinner } from '../ui'

function Evidence({ urls }: { urls: string[] }) {
  if (!urls.length) return null
  return (
    <ul className="evidence-list">
      {urls.map((u) => (
        <li key={u}>
          <a href={u} target="_blank" rel="noreferrer">
            {u}
          </a>
        </li>
      ))}
    </ul>
  )
}

interface ConfirmHandlers {
  convId: number | null
  decided: Record<string, 'approved' | 'denied'>
  busy: boolean
  onDecide: (idx: number, decision: 'approve' | 'deny') => void
}

function agentIndexMap(events: AgentStreamEvent[]): Array<{ evt: AgentStreamEvent; index: number }> {
  let idx = -1
  return events.map((evt) => {
    if (evt.kind !== 'user' && evt.kind !== 'start' && evt.kind !== 'done') idx += 1
    return { evt, index: idx }
  })
}

function StepCard({ evt, stepIndex, confirm }: { evt: AgentStreamEvent; stepIndex?: number; confirm?: ConfirmHandlers }) {
  if (evt.kind === 'start' || evt.kind === 'done' || evt.kind === 'user') return null
  if (evt.kind === 'thought') {
    return (
      <div className="chat-step">
        <span className="step-tag">thought</span>
        <span className="step-detail">{evt.detail || '…'}</span>
      </div>
    )
  }
  if (evt.kind === 'tool') {
    return (
      <div className="chat-step">
        <span className="step-tag tool">tool {evt.label}</span>
        <code className="step-args">{evt.detail}</code>
      </div>
    )
  }
  if (evt.kind === 'result') {
    return (
      <div className="chat-step">
        <span className="step-tag result">result</span>
        <span className="step-detail">{evt.detail}</span>
        <Evidence urls={evt.evidence} />
      </div>
    )
  }
  if (evt.kind === 'evidence') {
    return (
      <div className="chat-step">
        <span className="step-tag result">evidence</span>
        <Evidence urls={evt.evidence} />
      </div>
    )
  }
  if (evt.kind === 'confirm') {
    const key = evt.data?.url as string | undefined
    const decided = stepIndex !== undefined && confirm
      ? confirm.decided[`${confirm.convId}:${stepIndex}`]
      : undefined
    const disabled = !confirm || confirm.busy || decided !== undefined || confirm.convId === null
    return (
      <div className="chat-step confirm">
        <span className="step-tag tool">confirmation required</span>
        <span className="step-detail">{evt.detail}</span>
        <Evidence urls={evt.evidence} />
        <div className="confirm-actions">
          <button
            type="button"
            className="btn btn-sm"
            disabled={disabled}
            onClick={() => stepIndex !== undefined && confirm?.onDecide(stepIndex, 'approve')}
          >
            {decided === 'approved' ? 'Approved · created pending action' : 'Approve removal'}
          </button>
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            disabled={disabled}
            onClick={() => stepIndex !== undefined && confirm?.onDecide(stepIndex, 'deny')}
          >
            {decided === 'denied' ? 'Denied · no action' : 'Deny'}
          </button>
          {key && <span className="muted confirm-ref">{key}</span>}
        </div>
      </div>
    )
  }
  if (evt.kind === 'error') {
    return <div className="error-banner">{evt.detail || evt.label}</div>
  }
  return null
}

function Readback({ steps }: { steps: AgentStreamEvent[] }) {
  return (
    <>
      {steps.map((s, i) => (
        <StepCard key={`${s.kind}-${i}`} evt={s} />
      ))}
    </>
  )
}

export default function Agent() {
  const [status, setStatus] = useState<AgentStatus | null>(null)
  const [events, setEvents] = useState<AgentStreamEvent[]>([])
  const [done, setDone] = useState<AgentDone | null>(null)
  const [convId, setConvId] = useState<number | null>(null)
  const [decided, setDecided] = useState<Record<string, 'approved' | 'denied'>>({})
  const [draft, setDraft] = useState('')
  const [approveHybrid, setApproveHybrid] = useState(false)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [history, setHistory] = useState<AgentConversation[] | null>(null)
  const [detail, setDetail] = useState<AgentConversationDetail | null>(null)

  useEffect(() => {
    api.getAgentStatus().then(setStatus).catch(() => {})
  }, [])

  const decide = async (stepIndex: number, decision: 'approve' | 'deny') => {
    if (convId === null || running) return
    try {
      await api.confirmAgentRemoval(convId, stepIndex, decision)
      setDecided((prev) => ({
        ...prev,
        [`${convId}:${stepIndex}`]: decision === 'approve' ? 'approved' : 'denied',
      }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const send = async () => {
    const prompt = draft.trim()
    if (!prompt || running) return
    setDraft('')
    setError('')
    setDone(null)
    setConvId(null)
    setRunning(true)
    setEvents((prev) => [
      ...prev,
      { kind: 'user', label: 'user', detail: prompt, evidence: [], data: {} },
    ])
    try {
      const result = await api.streamAgentChat(prompt, approveHybrid, (evt) => {
        if (evt.conversationId !== undefined) setConvId(evt.conversationId)
        setEvents((prev) => [...prev, evt])
      })
      setDone(result)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }

  const loadHistory = async () => {
    if (history !== null) return
    try {
      setHistory(await api.getAgentConversations())
    } catch {
      /* silent */
    }
  }

  const openHistory = async (id: number) => {
    try {
      setDetail(await api.getAgentConversation(id))
    } catch {
      /* silent */
    }
  }

  if (!status) return <div className="page"><Spinner /></div>

  const blocked = status.enabled && !status.configured
  const finalAnswer = done ? done.answer : ''

  return (
    <div className="page">
      <h2>Agent investigator</h2>
      <p className="muted">
        Chat se agent (Colab 27B / local Ollama) khud tools chala kar aapke apne
        publicly-exposed data ke traces dhondta hai — evidence ke sath, aur koi
        state change confirmation ke baghair nahi.
      </p>
      <div className="cards">
        <div className="card"><span className="card-label">Agent enabled</span><span className="card-value">{String(status.enabled)}</span></div>
        <div className="card"><span className="card-label">Brain backend</span><span className="card-value">{status.backend}</span></div>
      </div>

      {blocked && (
        <div className="error-banner">
          Agent brain nahi mila (no Colab/local Ollama reachable). Deterministic
          scans phir bhi chalte hain — chat abhi unavailable hai.
        </div>
      )}
      {error && <ErrorBanner message={error} />}

      <div className="chat-layout">
        <div className="chat-log">
          {agentIndexMap(events).map((entry, i) => (
            <StepCard
              key={`${entry.evt.kind}-${i}`}
              evt={entry.evt}
              stepIndex={entry.evt.kind === 'confirm' ? entry.index : undefined}
              confirm={{ convId, decided, busy: running, onDecide: decide }}
            />
          ))}
          {running && <Spinner />}
          {finalAnswer && !running && <div className="chat-answer">{finalAnswer}</div>}
          {events.length === 0 && !running && (
            <p className="muted">
              Example: "mera email kahan kahan exposed hai?" · "meri photo kahan
              post ho sakti hai?" (hybrid approve karo) · "kya password breach
              mein hai?" (k-anonymity, ephemeral).
            </p>
          )}
        </div>

        <form
          className="chat-form"
          onSubmit={(e) => {
            e.preventDefault()
            void send()
          }}
        >
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Apna goal likhein (own data)..."
            rows={3}
            disabled={running || status.enabled === false}
          />
          <div className="chat-row">
            <label className="chat-check">
              <input
                type="checkbox"
                checked={approveHybrid}
                onChange={(e) => setApproveHybrid(e.target.checked)}
                disabled={running || status.enabled === false}
              />
              Hybrid approve — third-party network tools (reverse search, breach range) chala sakta hai
            </label>
            <button className="btn" type="submit" disabled={running || !draft.trim() || status.enabled === false}>
              {running ? 'Running…' : 'Investigate'}
            </button>
          </div>
        </form>

        <h3>Conversation history</h3>
        <button className="btn btn-ghost" type="button" onClick={() => void loadHistory()}>
          Load history
        </button>
        {history && history.length === 0 && <p className="muted">No conversations yet.</p>}
        {history && history.length > 0 && (
          <ul className="history-list">
            {history.map((c) => (
              <li key={c.id}>
                <button type="button" className="history-item" onClick={() => void openHistory(c.id)}>
                  #{c.id} {c.title} <span className="muted">· {c.status}{c.hybridApproved ? ' · hybrid' : ''}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {detail && (
          <div className="history-detail">
            <button type="button" className="btn btn-ghost" onClick={() => setDetail(null)}>
              Close
            </button>
            {detail.messages.map((msg) => (
              <div key={msg.id} className="history-msg">
                <strong>{msg.role}</strong>
                {msg.content && <p>{msg.content}</p>}
                {msg.steps && <Readback steps={msg.steps} />}
                {msg.answer && <div className="chat-answer">{msg.answer}</div>}
                {msg.blocked && <div className="error-banner">agent blocked (no brain)</div>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}