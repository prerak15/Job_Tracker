import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { CACHE_KEYS, readCache, writeCache } from '../cache'

const EXAMPLES = [
  'Paste a job posting to log it',
  '“Rejected from Acme”',
  '“Who should I follow up with?”',
  '“Solved LIS in 40m, missed the binary search trick”',
  '“Tailor my master resume for the Acme role”',
]

export default function ChatPanel({ onClose, onDataChanged, prompt }) {
  // Restored together: the transcript is what you read, and the session id is
  // what makes the next message continue that conversation rather than start a
  // new one. The Agent SDK persists sessions itself, so a resumed id survives a
  // backend restart; if it ever doesn't, the turn fails into the panel as a
  // message and "New chat" is right there.
  const [messages, setMessages] = useState(() => readCache(CACHE_KEYS.chatMessages, []))
  const [sessionId, setSessionId] = useState(() => readCache(CACHE_KEYS.chatSession, null))
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [health, setHealth] = useState(null)
  const bodyRef = useRef(null)
  const busyRef = useRef(false)
  const lastPrompt = useRef(null)

  useEffect(() => {
    api.chat.health().then(setHealth).catch(() => setHealth({ ok: false }))
  }, [])

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  // Cached at turn boundaries, never per token: `messages` changes on every
  // streamed character, and mirroring that into storage would be hundreds of
  // synchronous writes a second. The guard means a refresh mid-answer restores
  // the last *completed* turn rather than half a sentence.
  useEffect(() => {
    if (busy) return
    writeCache(CACHE_KEYS.chatMessages, messages)
    writeCache(CACHE_KEYS.chatSession, sessionId)
  }, [busy, messages, sessionId])

  // A dashboard button (e.g. "Generate resume") hands us a ready-made prompt.
  // Each click carries a new token so the same text can be sent twice.
  useEffect(() => {
    if (!prompt || prompt.token === lastPrompt.current || busyRef.current) return
    lastPrompt.current = prompt.token
    send(prompt.text)
  })

  async function send(override) {
    const text = (override ?? input).trim()
    if (!text || busyRef.current) return

    if (override === undefined) setInput('')
    busyRef.current = true
    setBusy(true)
    setMessages((m) => [...m, { role: 'user', text }, { role: 'assistant', text: '', tools: [] }])

    let touchedData = false
    try {
      await api.chat.send(text, sessionId, (event) => {
        setMessages((prev) => {
          const next = [...prev]
          const last = { ...next[next.length - 1] }
          if (event.type === 'text') {
            last.text += event.text
          } else if (event.type === 'tool') {
            last.tools = [...last.tools, event.name]
            if (!event.name.startsWith('list_') && !event.name.startsWith('get_')) {
              touchedData = true
            }
          } else if (event.type === 'error') {
            last.error = event.message
          }
          next[next.length - 1] = last
          return next
        })
        if (event.type === 'done' && event.session_id) setSessionId(event.session_id)
      })
    } catch (err) {
      setMessages((prev) => {
        const next = [...prev]
        next[next.length - 1] = { ...next[next.length - 1], error: String(err) }
        return next
      })
    } finally {
      busyRef.current = false
      setBusy(false)
      // Any write tool means the dashboard is now stale.
      if (touchedData) onDataChanged()
    }
  }

  return (
    <aside className="chat">
      <div className="chat-head">
        <strong style={{ flex: 1, fontSize: 13 }}>Assistant</strong>
        {health && (
          <span className="small muted">
            {health.ok
              ? health.auth === 'subscription'
                ? 'Claude subscription'
                : 'API key'
              : 'not connected'}
          </span>
        )}
        <button className="btn ghost small" onClick={onClose}>
          Close
        </button>
      </div>

      <div className="chat-body" ref={bodyRef}>
        {health && !health.ok && (
          <div className="msg error">
            {health.error} {health.hint}
          </div>
        )}

        {messages.length === 0 && (
          <div>
            <p className="chat-hint">
              Tell it what happened in plain language and it updates the tracker for you.
            </p>
            {EXAMPLES.map((e) => (
              <div className="tool-chip" key={e} style={{ display: 'block', marginBottom: 5 }}>
                {e}
              </div>
            ))}
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.tools?.length > 0 && (
              <div className="tool-trace">
                {m.tools.map((t, n) => (
                  <span className="tool-chip" key={n}>
                    {t.replace(/_/g, ' ')}
                  </span>
                ))}
              </div>
            )}
            <span className={busy && i === messages.length - 1 && !m.text ? 'blink' : ''}>
              {m.text}
            </span>
            {m.error && <div className="msg error">{m.error}</div>}
          </div>
        ))}
      </div>

      <div className="chat-foot">
        <textarea
          placeholder="Paste a posting, or say what happened…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) send()
          }}
          disabled={busy}
        />
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button className="btn primary" onClick={() => send()} disabled={busy || !input.trim()}>
            {busy ? 'Working…' : 'Send'}
          </button>
          <span className="small muted">Ctrl+Enter</span>
          {sessionId && (
            <button
              className="btn ghost small"
              style={{ marginLeft: 'auto' }}
              onClick={() => {
                // Clearing the state is enough — the effect above is the only
                // writer for these keys, and it persists the cleared
                // transcript on the very next render.
                setSessionId(null)
                setMessages([])
              }}
            >
              New chat
            </button>
          )}
        </div>
      </div>
    </aside>
  )
}
